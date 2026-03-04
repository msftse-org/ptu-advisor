"""LLM Provider abstraction for PTU Advisor.

This module provides a clean abstraction over different LLM providers,
allowing the PTU Advisor to use Foundry, OpenAI, or local models.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMConfig(BaseModel):
    """Configuration for LLM provider."""

    model_config = ConfigDict(validate_assignment=True)
    
    # Provider type
    provider: Literal["azure", "openai", "mock"] = "azure"
    
    # Model settings
    model: str = "gpt-4o"
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1500, ge=1)
    
    # Azure OpenAI specific
    azure_endpoint: Optional[str] = None
    azure_deployment: Optional[str] = None
    api_version: str = "2024-12-01-preview"
    
    # OpenAI specific
    openai_api_key: Optional[str] = None
    
    # Caching
    enable_cache: bool = True
    cache_ttl_seconds: int = 3600  # 1 hour
    
    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Create config from environment variables."""
        return cls(
            provider=os.getenv("PTU_ADVISOR_LLM_PROVIDER", "azure"),
            model=os.getenv("PTU_ADVISOR_LLM_MODEL", "gpt-4o"),
            temperature=float(os.getenv("PTU_ADVISOR_LLM_TEMPERATURE", "0.3")),
            max_tokens=int(os.getenv("PTU_ADVISOR_LLM_MAX_TOKENS", "1500")),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )


class LLMResponse(BaseModel):
    """Response from LLM provider."""
    
    content: str
    model: str
    usage: Dict[str, int] = Field(default_factory=dict)
    cached: bool = False


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._cache: Dict[str, LLMResponse] = {}
    
    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs
    ) -> LLMResponse:
        """Generate a response from the LLM."""
        pass
    
    def generate_sync(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs
    ) -> LLMResponse:
        """Synchronous wrapper for generate."""
        import asyncio

        try:
            asyncio.get_running_loop()
            # Already in an async context (e.g. Streamlit, Jupyter)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self.generate(system_prompt, user_prompt, **kwargs),
                )
                return future.result()
        except RuntimeError:
            # No running event loop — safe to use asyncio.run()
            return asyncio.run(
                self.generate(system_prompt, user_prompt, **kwargs)
            )
    
    def _get_cache_key(self, system_prompt: str, user_prompt: str) -> str:
        """Generate cache key from prompts."""
        import hashlib
        combined = f"{system_prompt}|||{user_prompt}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def _check_cache(self, cache_key: str) -> Optional[LLMResponse]:
        """Check if response is cached."""
        if not self.config.enable_cache:
            return None
        
        if cache_key in self._cache:
            response = self._cache[cache_key]
            response.cached = True
            return response
        
        return None
    
    def _store_cache(self, cache_key: str, response: LLMResponse) -> None:
        """Store response in cache."""
        if self.config.enable_cache:
            self._cache[cache_key] = response


class AzureOpenAIProvider(LLMProvider):
    """Foundry LLM provider."""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None
    
    def _get_client(self):
        """Lazy initialization of Foundry client."""
        if self._client is None:
            try:
                from azure.ai.projects import AIProjectClient
                from azure.identity import DefaultAzureCredential
                
                # Try using AI Foundry SDK first
                if self.config.azure_endpoint:
                    self._client = AIProjectClient(
                        endpoint=self.config.azure_endpoint,
                        credential=DefaultAzureCredential(),
                    )
                    self._client_type = "foundry"
                else:
                    raise ImportError("Falling back to OpenAI SDK")
                    
            except ImportError:
                # Fall back to OpenAI SDK with Azure
                from openai import AzureOpenAI
                from azure.identity import DefaultAzureCredential, get_bearer_token_provider
                
                if not self.config.azure_endpoint:
                    raise ValueError(
                        "AZURE_OPENAI_ENDPOINT environment variable is required"
                    )
                
                token_provider = get_bearer_token_provider(
                    DefaultAzureCredential(),
                    "https://cognitiveservices.azure.com/.default"
                )
                
                self._client = AzureOpenAI(
                    azure_endpoint=self.config.azure_endpoint,
                    azure_ad_token_provider=token_provider,
                    api_version=self.config.api_version,
                )
                self._client_type = "openai"
        
        return self._client
    
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs
    ) -> LLMResponse:
        """Generate response using Foundry."""
        # Check cache first
        cache_key = self._get_cache_key(system_prompt, user_prompt)
        cached = self._check_cache(cache_key)
        if cached:
            return cached
        
        client = self._get_client()
        
        temperature = kwargs.get("temperature", self.config.temperature)
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        if self._client_type == "foundry":
            # Use Foundry SDK
            response = client.inference.chat.complete(
                model=self.config.azure_deployment or self.config.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            result = LLMResponse(
                content=response.choices[0].message.content,
                model=self.config.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
            )
        else:
            # Use OpenAI SDK
            response = client.chat.completions.create(
                model=self.config.azure_deployment or self.config.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            result = LLMResponse(
                content=response.choices[0].message.content,
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
            )
        
        # Cache the result
        self._store_cache(cache_key, result)
        
        return result


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider (non-Azure)."""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None
    
    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            from openai import OpenAI
            
            api_key = self.config.openai_api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is required")
            
            self._client = OpenAI(api_key=api_key)
        
        return self._client
    
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs
    ) -> LLMResponse:
        """Generate response using OpenAI."""
        # Check cache first
        cache_key = self._get_cache_key(system_prompt, user_prompt)
        cached = self._check_cache(cache_key)
        if cached:
            return cached
        
        client = self._get_client()
        
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
        )
        
        result = LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        )
        
        # Cache the result
        self._store_cache(cache_key, result)
        
        return result


class MockProvider(LLMProvider):
    """Mock LLM provider for testing and demos without API access."""
    
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs
    ) -> LLMResponse:
        """Return a mock response for demo purposes."""
        # Parse the user prompt to extract recommendation type
        # Check for NOT_RECOMMENDED first (more specific)
        if "PTU_NOT_RECOMMENDED" in user_prompt or "Decision**: PTU_NOT" in user_prompt:
            content = self._generate_payg_explanation(user_prompt)
        elif "BORDERLINE" in user_prompt or "Decision**: BORDERLINE" in user_prompt:
            content = self._generate_borderline_explanation(user_prompt)
        elif "PTU_RECOMMENDED" in user_prompt or "Decision**: PTU_REC" in user_prompt:
            content = self._generate_ptu_recommended_explanation(user_prompt)
        else:
            # Default to borderline if unclear
            content = self._generate_borderline_explanation(user_prompt)
        
        return LLMResponse(
            content=content,
            model="mock-gpt-4o",
            usage={"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
            cached=False,
        )
    
    def _generate_ptu_recommended_explanation(self, prompt: str) -> str:
        return """## AI Analysis Summary

Your deployment exhibits the **classic hallmarks of a PTU-ready workload**. Here's what stands out:

### 🔥 Critical Observations

1. **Consistent High Throughput**: Your token consumption maintains a steady baseline with predictable peaks during business hours. This is exactly the pattern PTU is designed to serve efficiently.

2. **Throttling Under Pressure**: The 8%+ throttling rate indicates your current PAYG quota is becoming a bottleneck. This means real users are experiencing delays or failures—PTU eliminates this entirely.

3. **Latency-Sensitive Workload**: Your P95 latency spikes during peak hours suggest capacity contention. PTU provides dedicated capacity, ensuring consistent sub-second responses.

### 💡 Key Insight

Your workload has matured from experimental to production-grade. The cost predictability and guaranteed capacity of PTU will provide better user experience AND likely lower effective cost per token at your volume.

### ⚡ Recommended Action

Start with **Global Provisioned** deployment for lowest latency. Size at your P95 TPM + 20% safety margin. Consider enabling spillover to PAYG for unexpected spikes."""

    def _generate_payg_explanation(self, prompt: str) -> str:
        return """## AI Analysis Summary

Your deployment is **well-suited for Pay-As-You-Go (PAYG)** pricing. Here's the reasoning:

### 📊 Usage Pattern Analysis

1. **Sporadic Usage**: Your token consumption shows significant variance with many idle periods. PTU would charge for capacity you're not using 60%+ of the time.

2. **Low Throttling**: With <1% throttling rate, your current quota is more than sufficient. There's no capacity pressure driving the need for reserved throughput.

3. **Development/Test Characteristics**: The unpredictable request patterns suggest this deployment is used for experimentation, testing, or low-volume internal tools.

### 💰 Cost Perspective

At current usage levels, PAYG costs approximately **$X/month** while the minimum PTU deployment would cost **$Y/month**—a significant premium for capacity you won't utilize.

### 🔮 When to Revisit

Set up monitoring alerts for:
- Throttling rate exceeds 3% consistently
- Daily TPM grows by 50%+
- P95 latency exceeds your SLA threshold

These would signal it's time to re-evaluate PTU."""

    def _generate_borderline_explanation(self, prompt: str) -> str:
        return """## AI Analysis Summary

Your deployment sits in an **interesting middle ground**. The data tells a nuanced story:

### ⚖️ Mixed Signals

**Favoring PTU:**
- Moderate throttling suggests growing capacity needs
- Business hours show consistent utilization

**Favoring PAYG:**
- Significant weekend/off-hours idle time
- Workload variability creates sizing challenges

### 🧪 Recommendation: Test Before Committing

1. **Run a load test** simulating 2x current peak traffic
2. **Monitor for 2 more weeks** to establish pattern confidence
3. **Calculate break-even**: At what utilization does PTU become cheaper?

### 💡 Hybrid Approach

Consider a **spillover strategy**: Deploy PTU sized at 60% of peak (covering your baseline) and let spikes overflow to PAYG. This provides cost predictability while maintaining flexibility."""


def get_provider(config: Optional[LLMConfig] = None) -> LLMProvider:
    """Factory function to get appropriate LLM provider."""
    if config is None:
        config = LLMConfig.from_env()
    
    provider_map = {
        "azure": AzureOpenAIProvider,
        "openai": OpenAIProvider,
        "mock": MockProvider,
    }
    
    provider_class = provider_map.get(config.provider.lower())
    if provider_class is None:
        raise ValueError(f"Unknown provider: {config.provider}")
    
    return provider_class(config)
