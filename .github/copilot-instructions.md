# PTU Advisor - AI Agent Instructions

## Project Overview

PTU Advisor is a Python CLI tool that analyzes Azure OpenAI deployments and recommends whether to use **Provisioned Throughput Units (PTU)** or stay with **Pay-As-You-Go (PAYG)** pricing.

### Project Structure

```
ptu-recommander/
├── ptu_advisor/
│   ├── __init__.py
│   ├── cli.py                    # Typer CLI commands
│   ├── config.py                 # Configuration dataclasses
│   ├── auth.py                   # Azure authentication
│   ├── demo.py                   # Demo scenarios with simulated data
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── engine.py             # DecisionEngine - main analysis logic
│   │   └── dimensions.py         # 4-dimension analyzers
│   ├── metrics/
│   │   ├── __init__.py
│   │   ├── models.py             # Data models (DeploymentMetrics, TimeSeries)
│   │   └── collector.py          # Azure Monitor metrics collector
│   ├── visualization/
│   │   ├── __init__.py
│   │   └── charts.py             # Matplotlib chart generation
│   ├── report/
│   │   ├── __init__.py
│   │   ├── generator.py          # HTML report generator
│   │   └── templates/
│   │       └── report.html       # Jinja2 HTML template
│   └── dashboard/
│       ├── __init__.py
│       └── app.py                # Streamlit interactive dashboard
├── outputs/                      # Generated reports
├── pyproject.toml
└── README.md
```

---

## Critical Data Models

### TimeSeries (ptu_advisor/metrics/models.py)

The `TimeSeries` dataclass represents time-series metric data:

```python
@dataclass
class TimeSeries:
    timestamps: List[datetime]
    values: List[float]
    metric_name: str
    unit: str = ""
    
    # Properties available:
    @property
    def mean(self) -> float        # Average value
    @property
    def std(self) -> float         # Standard deviation (NOT std_dev!)
    @property
    def cv(self) -> float          # Coefficient of variation
    @property
    def min(self) -> float         # Minimum value
    @property
    def max(self) -> float         # Maximum value
    @property
    def p50(self) -> float         # 50th percentile
    @property
    def p95(self) -> float         # 95th percentile
    @property
    def p99(self) -> float         # 99th percentile
    @property
    def total(self) -> float       # Sum of all values
    @property
    def non_zero_count(self) -> int
    @property
    def zero_percentage(self) -> float
```

**⚠️ IMPORTANT**: Use `.std` NOT `.std_dev` for standard deviation!

### DeploymentMetrics (ptu_advisor/metrics/models.py)

```python
@dataclass
class DeploymentMetrics:
    # Metadata
    deployment_name: str
    model_name: str
    start_time: datetime           # NOT analysis_start_time!
    end_time: datetime             # NOT analysis_end_time!
    
    # Time axis
    timestamps: List[datetime] = field(default_factory=list)
    
    # Request metrics (all are Optional[TimeSeries])
    requests_per_minute: Optional[TimeSeries] = None
    successful_requests: Optional[TimeSeries] = None
    throttled_requests: Optional[TimeSeries] = None
    
    # Token metrics
    prompt_tokens: Optional[TimeSeries] = None
    completion_tokens: Optional[TimeSeries] = None
    tokens_per_minute: Optional[TimeSeries] = None
    
    # Latency metrics (SEPARATE TimeSeries for each percentile!)
    time_to_first_byte_p50: Optional[TimeSeries] = None
    time_to_first_byte_p95: Optional[TimeSeries] = None
    time_to_first_byte_p99: Optional[TimeSeries] = None
    
    # PTU metrics
    ptu_utilization: Optional[TimeSeries] = None
    
    # Computed properties
    @property
    def total_requests(self) -> int
    @property
    def throttling_rate(self) -> float  # Returns decimal (0.05 = 5%)
    @property
    def avg_tokens_per_request(self) -> float
```

**⚠️ IMPORTANT Attribute Mappings**:

| ❌ WRONG | ✅ CORRECT |
|----------|-----------|
| `metrics.requests` | `metrics.successful_requests`, `metrics.throttled_requests` |
| `metrics.requests.total` | `metrics.total_requests` |
| `metrics.requests.throttled` | `metrics.throttled_requests.total` |
| `metrics.time_to_first_token` | `metrics.time_to_first_byte_p50/p95/p99` |
| `ttft.p50_avg` | `metrics.time_to_first_byte_p50.mean` |
| `metrics.analysis_start_time` | `metrics.start_time` |
| `metrics.model_version` | ❌ Does not exist |
| `metrics.sku_name` | ❌ Does not exist |
| `metrics.data_points_count` | `len(metrics.timestamps)` |
| `tpm.std_dev` | `tpm.std` |
| `dim_data.dimension` | `dim_data.name` |
| `dim_data.ptu_favorable` | `dim_data.is_positive` |
| `dim_data.metrics` | `dim_data.key_metrics` |
| `AnalysisDimensions` | `DimensionScores` |
| `Recommendation.PAYG_OPTIMAL` | `Recommendation.PTU_NOT_RECOMMENDED` |
| `Recommendation.FURTHER_ANALYSIS` | `Recommendation.BORDERLINE` |

### DimensionResult (ptu_advisor/metrics/models.py)

```python
@dataclass
class DimensionResult:
    name: str                              # Name of the dimension
    score: DimensionScore                  # POSITIVE, NEUTRAL, NEGATIVE, INSUFFICIENT
    confidence: float                      # 0.0 to 1.0
    summary: str                           # One-line summary
    explanation: str                       # Detailed explanation
    key_metrics: Dict[str, float] = field(default_factory=dict)

    @property
    def is_positive(self) -> bool:         # Whether this dimension favors PTU
```

**⚠️ IMPORTANT**:
- Use `.name` NOT `.dimension`!
- Use `.is_positive` NOT `.ptu_favorable`!
- Use `.key_metrics` NOT `.metrics`!
- Use `.explanation` NOT `.reasoning`!

### AnalysisResult (ptu_advisor/metrics/models.py)

```python
@dataclass
class AnalysisResult:
    recommendation: Recommendation  # PTU_RECOMMENDED, BORDERLINE, PTU_NOT_RECOMMENDED
    dimensions: DimensionScores
    confidence: float              # 0.0-1.0
    summary: str
    explanation: str
    what_would_change: str
    data_quality: str
    analysis_period: str
    cost_estimate: Optional[Dict[str, Any]] = None
```

### DimensionScores (ptu_advisor/metrics/models.py)

```python
@dataclass
class DimensionScores:
    workload_shape: DimensionResult
    capacity_pressure: DimensionResult
    latency_sensitivity: DimensionResult
    load_predictability: DimensionResult

    @property
    def all_dimensions(self) -> List[DimensionResult]
    @property
    def positive_count(self) -> int
    @property
    def average_confidence(self) -> float
```

---

## Configuration Classes

### AnalysisConfig (ptu_advisor/config.py)

Required when creating `DecisionEngine`:

```python
from ptu_advisor.config import AnalysisConfig

# DecisionEngine requires AnalysisConfig
config = AnalysisConfig(
    resource_group="my-rg",
    workspace="my-workspace", 
    deployment="my-deployment",
    lookback_days=14  # Optional, defaults to 14
)

engine = DecisionEngine(config)
analysis = engine.analyze(metrics)
```

---

## Demo Mode

### Generating Demo Data

```python
from ptu_advisor.demo import generate_demo_metrics, DemoScenario, SCENARIOS

# Available scenarios
# DemoScenario.PTU_RECOMMENDED      - High throttling, stable workload
# DemoScenario.PTU_NOT_RECOMMENDED  - Low usage, variable workload
# DemoScenario.BORDERLINE           - Mixed signals

# Generate metrics for a scenario
metrics, scenario_config = generate_demo_metrics(DemoScenario.PTU_RECOMMENDED)

# scenario_config is a ScenarioConfig with:
# - name: str
# - description: str
# - deployment_name: str
# - model_name: str
# - tpm_mean, throttling_rate, etc.
```

---

## Streamlit Dashboard

### Running the Dashboard

```bash
cd ptu-recommander
streamlit run ptu_advisor/dashboard/app.py --server.port 8501 --server.headless true
```

### Common Streamlit Issues

1. **Deprecation Warnings**: 
   - Use `freq='h'` instead of `freq='H'` for hourly
   - Replace `use_container_width=True` with `width='stretch'`

2. **Caching Issues**: Streamlit caches function results. Use `st.cache_data(ttl=300)` with TTL.

3. **Import Errors**: Ensure correct imports:
   ```python
   from ptu_advisor.demo import generate_demo_metrics, DemoScenario, SCENARIOS
   from ptu_advisor.analysis.engine import DecisionEngine
   from ptu_advisor.config import AnalysisConfig, ThresholdConfig
   ```

---

## Common Debugging Patterns

### Accessing Metrics Correctly

```python
# ❌ WRONG
throttle_rate = metrics.requests.throttled / metrics.requests.total
latency_p95 = metrics.time_to_first_token.p95_avg

# ✅ CORRECT
throttle_rate = metrics.throttling_rate * 100  # Property returns decimal
latency_p95 = metrics.time_to_first_byte_p95.mean if metrics.time_to_first_byte_p95 else 0

# For total tokens
total_tokens = (
    (metrics.prompt_tokens.total if metrics.prompt_tokens else 0) +
    (metrics.completion_tokens.total if metrics.completion_tokens else 0)
)

# For request counts
total_requests = metrics.total_requests
throttled = int(metrics.throttled_requests.total) if metrics.throttled_requests else 0
successful = int(metrics.successful_requests.total) if metrics.successful_requests else 0
```

### Creating Latency Tables

```python
# ❌ WRONG - No single time_to_first_token object
ttft = metrics.time_to_first_token
values = [ttft.p50_avg, ttft.p95_avg, ttft.p99_avg]

# ✅ CORRECT - Separate TimeSeries for each percentile
p50 = metrics.time_to_first_byte_p50
p95 = metrics.time_to_first_byte_p95
p99 = metrics.time_to_first_byte_p99

latency_data = {
    'Percentile': ['P50', 'P95', 'P99'],
    'Average (ms)': [
        p50.mean if p50 else 0,
        p95.mean if p95 else 0,
        p99.mean if p99 else 0
    ],
    'Min (ms)': [
        p50.min if p50 else 0,
        p95.min if p95 else 0,
        p99.min if p99 else 0
    ],
    'Max (ms)': [
        p50.max if p50 else 0,
        p95.max if p95 else 0,
        p99.max if p99 else 0
    ]
}
```

### Working with DimensionResult

```python
# ❌ WRONG
st.write(dim_data.reasoning)

# ✅ CORRECT
st.write(dim_data.explanation)

# Accessing dimension scores
dims = analysis.dimensions
workload_score = dims.workload_shape.score        # DimensionScore enum (POSITIVE, NEUTRAL, etc.)
capacity_favorable = dims.capacity_pressure.is_positive  # True/False (property)
latency_explanation = dims.latency_sensitivity.explanation  # String
latency_confidence = dims.latency_sensitivity.confidence   # 0.0-1.0
```

---

## PTU Sizing Calculations

Based on Azure documentation. Model configs are now centralized in `ptu_advisor/config.py`:

```python
from ptu_advisor.config import get_model_config, MODEL_CAPACITY_CONFIGS

# Look up a model by name (fuzzy match)
config = get_model_config("gpt-4o (2024-11-20)")
# config.payg_tpm_quota       = 450_000
# config.input_tpm_per_ptu    = 2500
# config.output_ratio         = 3
# config.global_min_ptu       = 15
# config.regional_min_ptu     = 50

# PTU calculation formula
# Effective TPM = input_tokens + (output_tokens × output_ratio)
# PTU needed = (Peak TPM × safety_margin) / TPM_per_PTU
```

---

## Quick Reference: File Locations

| Component | File Path |
|-----------|-----------|
| Data models | `ptu_advisor/metrics/models.py` |
| Decision engine | `ptu_advisor/analysis/engine.py` |
| Dimension analyzers | `ptu_advisor/analysis/dimensions.py` || Model capacity configs | `ptu_advisor/config.py` |
| LLM explainer | `ptu_advisor/llm/explainer.py` |
| LLM prompts | `ptu_advisor/llm/prompts.py` || Demo scenarios | `ptu_advisor/demo.py` |
| Configuration | `ptu_advisor/config.py` |
| Streamlit dashboard | `ptu_advisor/dashboard/app.py` |
| HTML report template | `ptu_advisor/report/templates/report.html` |
| Report generator | `ptu_advisor/report/generator.py` |

---

## Testing Commands

```bash
# Run demo mode via CLI
python -m ptu_advisor.cli demo --scenario ptu-recommended

# List available scenarios
python -m ptu_advisor.cli demo-list

# Run Streamlit dashboard
streamlit run ptu_advisor/dashboard/app.py --server.port 8501 --server.headless true
```

---

## Error Resolution Checklist

When encountering `AttributeError`:

1. ✅ Check if using `.std` instead of `.std_dev`
2. ✅ Check if using `.explanation` instead of `.reasoning`
3. ✅ Check if using `.name` instead of `.dimension`
4. ✅ Check if using `.is_positive` instead of `.ptu_favorable`
5. ✅ Check if using `.key_metrics` instead of `.metrics`
6. ✅ Check if using `start_time`/`end_time` instead of `analysis_start_time`/`analysis_end_time`
7. ✅ Check if accessing `time_to_first_byte_p50/p95/p99` instead of `time_to_first_token`
8. ✅ Check if using `metrics.throttling_rate` (decimal) instead of calculating manually
9. ✅ Check if `DecisionEngine` is initialized with `AnalysisConfig`
10. ✅ Verify TimeSeries properties exist before accessing (e.g., `if metrics.tokens_per_minute:`)
11. ✅ Use `DimensionScores` NOT `AnalysisDimensions`
12. ✅ Use `Recommendation.PTU_NOT_RECOMMENDED` NOT `Recommendation.PAYG_OPTIMAL`
