---
name: ptu-advisor
description: Analyze Azure OpenAI and Foundry deployment metrics to recommend PTU (Provisioned Throughput Units) vs PAYG (Pay-As-You-Go) pricing. Use this skill when the user provides deployment metrics, usage data, or asks about PTU sizing, cost comparison, or capacity planning for Foundry models.
license: Complete terms in LICENSE.txt
---

# PTU Advisor Skill

This skill provides expert analysis of Foundry deployment metrics to determine whether PTU (Provisioned Throughput Units) or PAYG (Pay-As-You-Go) pricing is optimal for a given workload.

## When to Use This Skill

- User provides deployment metrics (TPM, throttling, latency, requests)
- User asks about PTU vs PAYG decision
- User needs PTU sizing recommendations
- User wants cost comparison analysis
- User asks about capacity planning for Foundry models

## Core Formulas

### PTU Sizing Formula

```
PTU_needed = ceil(peak_tpm × headroom_factor / tpm_per_ptu)

Where:
- peak_tpm = P95 or P99 of tokens per minute
- headroom_factor = 1.2 (20% buffer for burst handling)
- tpm_per_ptu = model-specific capacity (see table below)
- Minimum PTU = 10 (rounded to nearest 5)
```

**TPM per PTU by Model:**

| Model | Input TPM/PTU | Output Ratio |
|-------|---------------|--------------|
| GPT-5 | 3,400 | 1:8 |
| GPT-4.1 | 4,750 | 1:4 |
| GPT-4.1-mini | 23,750 | 1:4 |
| GPT-4o | 3,000 | 1:4 |
| GPT-4o-mini | 14,900 | 1:4 |
| GPT-3.5-Turbo | 59,400 | 1:4 |
| o1 | 3,000 | varies |
| o3-mini | 5,400 | varies |

**Default (for estimation):** 2,000 TPM/PTU

### Cost Comparison Formulas

**PAYG Monthly Cost:**
```
# Azure OpenAI Pricing (January 2026)
# GPT-4o Global: $2.50/1M input tokens, $10/1M output tokens
# Blended rate assuming 30% output: ~$4.75/1M tokens

payg_cost = (monthly_tokens / 1_000_000) × blended_rate_per_1M

monthly_tokens = avg_tpm × 60 × 24 × 30

# Add throttling impact (lost revenue/retry costs)
throttle_impact = payg_cost × throttle_rate × retry_cost_multiplier
total_payg = payg_cost + throttle_impact
```

**PTU Monthly Cost (Full PTU - sized to peak):**
```
# Azure Provisioned Pricing (January 2026)
# Global: $1/PTU-hour (no commitment)
# 1-Year Reserved: $2,652/year per PTU = $221/month = ~$0.30/hour (70% discount)

# Hourly pricing (no commitment)
ptu_hourly_cost = ptu_units × $1 × 24 × 30  # = ptu_units × $720/month

# With 1-year reservation (70% discount)
ptu_reserved_cost = ptu_units × $221/month  # = $2,652/year
```

### Spillover Strategy (Recommended)

**Reference:** [Azure Spillover Traffic Management](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/spillover-traffic-management)

The spillover strategy sizes PTU to cover **baseline usage** (not peak), and lets overflow traffic automatically route to a standard (PAYG) deployment.

**Key Principle:** Don't commit to peak TPM. Find an optimal baseline and pay PAYG rates only for overflow.

**Spillover Cost Formula:**
```python
# Step 1: Find baseline (P75 covers 75% of traffic)
baseline_tpm = percentile(tpm_values, 75)

# Step 2: Size PTU to baseline with small headroom
headroom = 1.1  # 10% for baseline (not 20% for peak)
ptu_baseline = ceil(baseline_tpm × headroom / tpm_per_ptu)
ptu_baseline = round_to_nearest_5(ptu_baseline)
ptu_capacity_tpm = ptu_baseline × tpm_per_ptu

# Step 3: Calculate spillover (tokens above PTU capacity)
spillover_tokens = []
for tpm in tpm_values:
    if tpm > ptu_capacity_tpm:
        spillover_tokens.append(tpm - ptu_capacity_tpm)

avg_spillover_tpm = mean(spillover_tokens)
spillover_monthly = avg_spillover_tpm × 60 × 24 × 30

# Step 4: Calculate hybrid cost
ptu_cost = ptu_baseline × hourly_rate × 720  # (× 0.35 for 1-yr reserved)
spillover_cost = (spillover_monthly / 1000) × payg_rate

total_hybrid = ptu_cost + spillover_cost
```

**When Spillover is Triggered:**
- PTU utilization reaches 100% (HTTP 429)
- Long context requests exceed PTU limits (HTTP 400)
- Server errors (HTTP 500/503)

**Benefits of Spillover:**
- Lower PTU commitment = lower fixed cost
- No over-provisioning for peak capacity
- Automatic overflow handling by Azure
- Pay PAYG only for actual overflow tokens

### Utilization Analysis Formulas

**Peak-to-Average Ratio:**
```
par = peak_tpm / avg_tpm

Interpretation:
- par < 1.5: Stable workload → PTU favorable
- par 1.5-2.5: Moderate variance → evaluate other factors
- par > 2.5: Spiky workload → PAYG may be better
```

**Sustained Utilization Rate:**
```
sustained_util = (hours_above_threshold / total_hours) × 100

Where threshold = avg_tpm × 0.3 (30% of average)

Interpretation:
- > 60%: Consistent usage → PTU favorable
- 40-60%: Moderate → consider other factors
- < 40%: Inconsistent → PAYG likely better
```

**Coefficient of Variation:**
```
cv = std_dev / mean

Interpretation:
- cv < 0.3: Very stable → strong PTU candidate (POSITIVE)
- cv 0.3-0.7: Moderate variance (NEUTRAL)
- cv > 0.7: High variance → PAYG may be better (NEGATIVE)
```

### Throttling Analysis

```
throttle_rate = throttled_requests / total_requests

Impact Assessment:
- < 1%: Minimal impact, PAYG acceptable
- 1-5%: Moderate impact, consider PTU
- > 5%: Significant impact, PTU strongly recommended

Business Impact Formula:
throttle_cost = throttle_rate × avg_request_value × requests_per_month
```

## Decision Framework

The PTU Advisor uses a **4-dimension scoring system**:

### Dimensions Analyzed

1. **Workload Shape** - Stability of token throughput (CV analysis)
2. **Capacity Pressure** - Throttling rate and utilization ceiling
3. **Latency Sensitivity** - P95/P99 latency patterns
4. **Load Predictability** - Day-over-day pattern consistency

Each dimension scores: **POSITIVE**, **NEUTRAL**, **NEGATIVE**, or **INSUFFICIENT**

### Decision Logic

```python
positive_count = count(dimensions where score == POSITIVE)

if positive_count >= 3:
    recommendation = "PTU_RECOMMENDED"
elif positive_count >= 2:
    recommendation = "BORDERLINE"
else:
    recommendation = "PTU_NOT_RECOMMENDED"
```

### Recommend PTU When:

1. **High sustained utilization** (>60% of time above 30% average)
2. **Significant throttling** (>1% of requests throttled)
3. **Latency-sensitive workload** (requires guaranteed <100ms TTFT)
4. **Predictable traffic patterns** (CV <0.5, PAR <2.0)
5. **Cost savings** (PTU reserved < PAYG + throttle impact)
6. **Guaranteed capacity needed** (business-critical SLAs)

### Recommend PAYG When:

1. **Variable/spiky workload** (PAR >2.5, CV >0.5)
2. **Low utilization** (<40% sustained)
3. **Development/testing** environment
4. **Unpredictable demand** (new application, unknown patterns)
5. **PTU cost exceeds PAYG** (even with throttle impact)

### Borderline Cases:

When signals are mixed, recommend:
- Collect 2-4 weeks additional data
- Run PTU trial deployment for comparison
- Consider hybrid approach (PTU base + PAYG overflow)

## Analysis Workflow

### Step 1: Collect Metrics
Required inputs:
- `tokens_per_minute`: TimeSeries with mean, p95, p99, std
- `requests_per_minute`: TimeSeries
- `throttled_requests`: Count or TimeSeries
- `latency_p50`, `latency_p95`, `latency_p99`: Milliseconds
- `analysis_period`: Days of data

### Step 2: Calculate Key Metrics
```python
# Usage metrics
avg_tpm = tokens_per_minute.mean
peak_tpm = tokens_per_minute.p95
monthly_tokens = avg_tpm * 60 * 24 * 30

# Variability metrics
par = peak_tpm / avg_tpm
cv = tokens_per_minute.std / avg_tpm
sustained_util = tokens_per_minute.sustained_utilization_rate(0.3)

# Throttling
throttle_rate = throttled_requests / total_requests
```

### Step 3: Size PTU Deployment
```python
# Model-specific TPM/PTU (default estimation)
tpm_per_ptu = 2000  # Conservative default

# Calculate with headroom
ptu_raw = peak_tpm * 1.2 / tpm_per_ptu
ptu_needed = max(10, int(ptu_raw + 0.5))  # Round, min 10
ptu_needed = ((ptu_needed + 4) // 5) * 5  # Round to nearest 5

# For Global/Data Zone deployments, minimum is 15
# For Regional deployments, minimum varies (25-50)
```

### Step 4: Cost Comparison
```python
# PAYG cost
payg_rate = 0.01  # $/1K tokens (varies by model)
payg_base = (monthly_tokens / 1000) * payg_rate
throttle_impact = payg_base * throttle_rate * 2
payg_total = payg_base + throttle_impact

# PTU cost
ptu_hourly = 0.06  # $/PTU/hour
ptu_monthly_full = ptu_needed * ptu_hourly * 24 * 30
ptu_reserved = ptu_monthly_full * 0.35  # 1-year reservation

# Savings
savings = payg_total - ptu_reserved
savings_pct = (savings / payg_total) * 100
```

### Step 5: Generate Recommendation
```python
# The engine uses dimension scoring, not just cost
# Analyze 4 dimensions and count positive scores

dimensions = [
    workload_shape_score,      # Based on CV
    capacity_pressure_score,   # Based on throttling
    latency_sensitivity_score, # Based on P95/P99
    load_predictability_score  # Based on patterns
]

positive_count = sum(1 for d in dimensions if d == "POSITIVE")

if positive_count >= 3:
    recommendation = "PTU_RECOMMENDED"
elif positive_count >= 2:
    recommendation = "BORDERLINE"
else:
    recommendation = "PTU_NOT_RECOMMENDED"

# Cost comparison is shown for context but not the primary decision factor
```

## Confidence Scoring

```python
def calculate_confidence(dimensions, metrics, config):
    # Average dimension confidence (each dimension has its own)
    dim_confidence = average([d.confidence for d in dimensions])
    
    # Data quantity factor
    data_points = len(metrics.timestamps)
    data_factor = min(1.0, data_points / config.min_data_points)  # default: 100
    
    # Analysis period factor
    days = config.lookback_days
    days_factor = min(1.0, days / config.min_days_for_confidence)  # default: 3
    
    # Combine factors (weighted average)
    return dim_confidence * 0.5 + data_factor * 0.3 + days_factor * 0.2
```

### Dimension-Specific Confidence

Each dimension calculates its own confidence:
- **Workload Shape**: `min(1.0, data_points / 500)`
- **Capacity Pressure**: `min(1.0, total_requests / 10000)`
- **Latency Sensitivity**: Based on latency data availability
- **Load Predictability**: Based on day-over-day data quality

## Output Format

When providing recommendations, structure the output as:

```
## 📊 Usage Summary
- Average TPM: X
- Peak TPM (P95): Y
- Throttling Rate: Z%
- Analysis Period: N days

## 💰 Cost Comparison
| Metric | PAYG | PTU (Reserved) |
|--------|------|----------------|
| Monthly Cost | $X | $Y |
| Throttle Impact | $Z | $0 |
| **Total** | **$A** | **$B** |

## 🎯 Recommendation
**[PTU RECOMMENDED / STAY WITH PAYG / BORDERLINE]**
- Confidence: X%
- Savings: $Y/month (Z%)

## 📋 Key Factors
1. [Primary reason]
2. [Secondary reason]
3. [Supporting evidence]

## 🚀 Next Steps
1. [Actionable recommendation]
2. [Follow-up action]
```

## References

- [PTU Concepts](https://learn.microsoft.com/azure/ai-services/openai/concepts/provisioned-throughput)
- [PTU Onboarding Guide](https://learn.microsoft.com/azure/ai-services/openai/how-to/provisioned-throughput-onboarding)
- [Foundry PTU Calculator](https://ai.azure.com/resource/calculator)
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)
- [PTU Reservation Documentation](https://aka.ms/oai/docs/ptum-reservations)
