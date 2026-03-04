# PTU Model Reference

This reference provides model-specific PTU capacity and pricing information sourced from Microsoft Learn documentation.

## Model Capacity Table

### Latest Azure OpenAI Models (GPT-4.1+, GPT-5)

| Model | Min PTU (Global/DZ) | Min PTU (Regional) | Increment | Input TPM/PTU | Output Ratio | Latency Target |
|-------|---------------------|-------------------|-----------|---------------|--------------|----------------|
| gpt-5 | 15 | 50 | 5/50 | 3,400 | 1:8 | 99% >50 TPS |
| gpt-4.1 | 15 | 50 | 5/50 | 4,750 | 1:4 | 99% >50 TPS |
| gpt-4.1-mini | 15 | 25 | 5/25 | 23,750 | 1:4 | 99% >80 TPS |
| gpt-4.1-nano | 15 | 25 | 5/25 | 59,400 | 1:4 | 99% >100 TPS |
| gpt-4o | 15 | 50 | 5/50 | 3,000 | 1:4 | 99% >80 TPS |
| gpt-4o-mini | 15 | 25 | 5/25 | 14,900 | 1:4 | 99% >90 TPS |
| o1 | 15 | 50 | 5/50 | 3,000 | varies | 99% >80 TPS |
| o3-mini | 15 | 25 | 5/25 | 5,400 | varies | 99% >90 TPS |
| o4-mini | 15 | 50 | 5/50 | 3,000 | varies | 99% >80 TPS |

### Previous Azure OpenAI Models

| Model | Min PTU (Global/DZ) | Min PTU (Regional) | Increment | Input TPM/PTU | Latency Target |
|-------|---------------------|-------------------|-----------|---------------|----------------|
| gpt-4 | 15 | 50 | 5/50 | 2,500 | 99% >25 TPS |
| gpt-4-turbo | 15 | 25 | 5/25 | 37,000 | 99% >33 TPS |
| gpt-35-turbo | 15 | 25 | 5/25 | 2,500 | 99% >66 TPS |
| gpt-4-32k | 15 | 25 | 5/50 | 230 | 99% >25 TPS |

### Direct from Azure Models (Foundry Models)

| Model | Min PTU (Global/DZ) | Increment | Input TPM/PTU | Output Ratio | Latency Target |
|-------|---------------------|-----------|---------------|--------------|----------------|
| Llama-3.3-70B-Instruct | 100 | 100 | 8,450 | 1:4 | 99% >50 TPS |
| DeepSeek-R1 | 100 | 100 | 4,000 | varies | 99% >50 TPS |
| DeepSeek-V3 | 100 | 100 | 4,000 | varies | 99% >50 TPS |

## Deployment Types

| Type | SKU Name | Data Residency | Minimum PTU | Use Case |
|------|----------|----------------|-------------|----------|
| Global Provisioned | GlobalProvisionedManaged | No guarantee | 15 | Highest availability, cost-effective |
| Data Zone Provisioned | DataZoneProvisionedManaged | Within data zone | 15 | Data residency within region group |
| Regional Provisioned | ProvisionedManaged | Single region | 25-50 | Strict data residency requirements |

## Pricing Tiers (January 2026)

Source: [Azure OpenAI Pricing](https://azure.microsoft.com/en-us/pricing/details/azure-openai/)

### PTU Provisioned Pricing

| Deployment Type | Hourly (No Commit) | Monthly Reserved | Annual Reserved |
|-----------------|-------------------|------------------|-----------------|
| Global | $1/PTU-hour | $260/PTU-month | $2,652/PTU-year |
| Data Zone | $1.10/PTU-hour | $286/PTU-month | $2,916/PTU-year |
| Regional | $2/PTU-hour | $286/PTU-month | $2,916/PTU-year |

### PAYG Token Pricing (per 1M tokens)

| Model | Input | Cached Input | Output |
|-------|-------|--------------|--------|
| GPT-4o Global | $2.50 | $1.25 | $10 |
| GPT-4o-mini Global | $0.15 | $0.075 | $0.60 |
| GPT-4.1 Global | $2 | $0.50 | $8 |
| GPT-4.1-mini Global | $0.40 | $0.10 | $1.60 |
| GPT-5 Global | $1.25 | $0.13 | $10 |

### Reserved Pricing Discounts
- **1-Year Reserved**: ~70% discount vs hourly
- **Monthly Reserved**: ~40% discount vs hourly

**Important**: Reservations are purchased separately from deployments. Deploy first, then purchase matching reservation.

## Sizing Guidelines

### Effective TPM Calculation
Output tokens consume more capacity than input tokens:

```
effective_tpm = input_tokens + (output_tokens × output_ratio)

# For GPT-4o (1:4 ratio):
effective_tpm = input_tokens + (output_tokens × 4)

# For GPT-5 (1:8 ratio):
effective_tpm = input_tokens + (output_tokens × 8)
```

### Headroom Recommendations
- **Production workloads**: 20% headroom (× 1.2) when sizing to peak
- **High-variability workloads**: 30% headroom (× 1.3) when sizing to peak
- **Mission-critical**: 40% headroom (× 1.4) when sizing to peak
- **Spillover strategy**: 10% headroom (× 1.1) when sizing to baseline

### Spillover Strategy (Recommended)

Instead of sizing PTU to peak capacity, use Azure's spillover feature:

1. **Size PTU to baseline** (P75 or average) - covers most traffic
2. **Enable spillover** to standard deployment - overflow goes to PAYG
3. **Pay only for actual overflow** - no wasted PTU capacity

Reference: [Spillover Traffic Management](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/spillover-traffic-management)

```python
# Spillover sizing formula
baseline_tpm = percentile(tpm_values, 75)  # P75 as baseline
ptu_baseline = ceil(baseline_tpm × 1.1 / tpm_per_ptu)  # 10% headroom

# Spillover triggers on:
# - HTTP 429 (PTU fully utilized)
# - HTTP 400 (long context exceeds PTU limits)  
# - HTTP 500/503 (server errors)
```

### Minimum Deployment Sizing
Always deploy at least:
- Global/Data Zone: 15 PTU minimum
- Regional: 25-50 PTU minimum (model-dependent)

## Throttling Behavior

PTU deployments use a leaky bucket algorithm:
1. Requests accepted until utilization reaches 100%
2. At 100%+ utilization, returns HTTP 429 with `retry-after-ms` header
3. Utilization decrements continuously based on PTU count

**Best Practices for 429 Handling:**
- Implement exponential backoff with jitter
- Consider fallback to PAYG deployment
- Monitor utilization metric to predict throttling

## Monitoring Metrics

Key Azure Monitor metrics for PTU deployments:
- `Provisioned-Managed Utilization V2`: Current capacity usage (%)
- `TokenTransaction`: Token consumption
- `SuccessfulCalls`: Completed requests
- `BlockedCalls`: Throttled requests (429s)

## Capacity Planning Checklist

1. ☐ Collect 2-4 weeks of usage data
2. ☐ Identify peak TPM (P95/P99)
3. ☐ Calculate input/output token ratio
4. ☐ Apply output multiplier for effective TPM
5. ☐ Add headroom (20-40%)
6. ☐ Round up to PTU increment
7. ☐ Verify quota availability
8. ☐ Deploy and test before purchasing reservation
9. ☐ Purchase matching reservation for cost savings

## Quick Reference: PTU Sizing Formula

```python
def calculate_ptu_needed(
    peak_input_tpm: float,
    peak_output_tpm: float,
    model: str,
    headroom: float = 1.2
) -> int:
    """Calculate PTU units needed for a workload."""
    
    # Model-specific values
    MODEL_CONFIG = {
        "gpt-5": {"tpm_per_ptu": 3400, "output_ratio": 8, "min": 15, "increment": 5},
        "gpt-4.1": {"tpm_per_ptu": 4750, "output_ratio": 4, "min": 15, "increment": 5},
        "gpt-4o": {"tpm_per_ptu": 3000, "output_ratio": 4, "min": 15, "increment": 5},
        "gpt-4o-mini": {"tpm_per_ptu": 14900, "output_ratio": 4, "min": 15, "increment": 5},
        "gpt-35-turbo": {"tpm_per_ptu": 59400, "output_ratio": 4, "min": 15, "increment": 5},
    }
    
    config = MODEL_CONFIG.get(model, MODEL_CONFIG["gpt-4o"])
    
    # Calculate effective TPM
    effective_tpm = peak_input_tpm + (peak_output_tpm * config["output_ratio"])
    
    # Apply headroom
    required_tpm = effective_tpm * headroom
    
    # Calculate PTU
    ptu_raw = required_tpm / config["tpm_per_ptu"]
    
    # Round to increment
    ptu_needed = math.ceil(ptu_raw / config["increment"]) * config["increment"]
    
    # Ensure minimum
    return max(ptu_needed, config["min"])
```
