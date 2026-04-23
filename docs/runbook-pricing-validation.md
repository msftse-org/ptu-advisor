# Runbook: Pricing Accuracy Validation

> **Owner**: PTU Advisor Team
> **Last Updated**: April 1, 2026
> **Frequency**: Monthly, or after Azure pricing announcements

---

## Purpose

Validate that PTU Advisor's resolved pricing rates match the official Azure OpenAI pricing page within 1% tolerance for all supported models.

---

## Prerequisites

- Access to the PTU Advisor API (local or deployed)
- Access to the [Azure OpenAI Pricing Page](https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/)
- `curl` or `httpx` for API calls

---

## Step 1: Fetch Resolved Rates from PTU Advisor

For each supported model, call the `/api/pricing/rates` endpoint:

```bash
MODELS=("gpt-5" "gpt-4.1" "gpt-4.1-mini" "gpt-4.1-nano" "gpt-4o" "gpt-4o-mini" "gpt-3.5-turbo" "o1" "o3-mini" "o4-mini")
REGION="eastus"
DTYPE="global"

for model in "${MODELS[@]}"; do
  echo "--- $model ---"
  curl -s "http://localhost:8000/api/pricing/rates?model=${model}&region=${REGION}&deployment_type=${DTYPE}" | python3 -m json.tool
done
```

Record the `payg_input_rate_per_million`, `payg_output_rate_per_million`, `ptu_hourly_rate`, and `pricing_source` for each model.

---

## Step 2: Collect Reference Rates from Azure

1. Navigate to [Azure OpenAI Pricing](https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/)
2. Select **Region: East US** and **Currency: USD**
3. For each model, record the Input and Output token prices (per 1M tokens)
4. Record the PTU hourly rate for the relevant deployment type (Global Provisioned Managed)

Alternatively, query the Azure Retail Prices API directly:

```bash
curl -s "https://prices.azure.com/api/retail/prices?\$filter=serviceName eq 'Foundry Models' and armRegionName eq 'eastus' and priceType eq 'Consumption' and contains(meterName, 'gpt 4o')" | python3 -m json.tool
```

---

## Step 3: Compare and Validate

For each model, compute the deviation:

```
deviation_pct = abs(resolved_rate - reference_rate) / reference_rate * 100
```

**Pass criteria**: deviation <= 1% for all rates.

| Model | Rate Type | Resolved | Reference | Deviation % | Pass? |
|-------|-----------|----------|-----------|-------------|-------|
| gpt-4o | Input | | | | |
| gpt-4o | Output | | | | |
| ... | ... | ... | ... | ... | ... |

---

## Step 4: Check Pricing Source

For each model, verify the `pricing_source` field:

- **`live`**: Rates were fetched from the Azure Retail Prices API. Best accuracy.
- **`cached`**: Rates are from cache (< 24h old). Acceptable.
- **`fallback`**: Rates are from static fallback. **Investigate why live fetch failed.**

If any model returns `fallback`:
1. Check if `httpx` is installed (`pip show httpx`)
2. Check network connectivity to `https://prices.azure.com`
3. Review application logs for `"Failed to fetch"` warnings
4. Verify the meter patterns in `MODEL_METER_PATTERNS` still match Azure's naming

---

## Step 5: Validate PTU Hourly Rates

PTU rates are fetched separately from PAYG rates. Verify:

1. **Global**: should be ~$1.00/PTU/hour
2. **Data Zone**: should be ~$1.10/PTU/hour
3. **Regional**: varies by region (see `STATIC_REGIONAL_PTU_RATES` in `price_resolver.py`)

```bash
for dtype in "global" "data_zone" "regional"; do
  echo "--- $dtype ---"
  curl -s "http://localhost:8000/api/pricing/rates?model=gpt-4o&region=eastus&deployment_type=${dtype}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'PTU hourly: \${d[\"ptu_hourly_rate\"]}')"
done
```

---

## Step 6: Document Results

Record validation results with:
- Date of validation
- Any models with > 1% deviation (and root cause)
- Any models returning `fallback` source (and remediation)
- Actions taken (e.g., updated static rates, fixed meter patterns)

---

## Troubleshooting

### Live fetch returns no results for a model
The Azure meter name format may have changed. Update `MODEL_METER_PATTERNS` in `ptu_advisor/cost/price_resolver.py` with the new meter name substring.

### Rates are 1000x off
Check the `unitOfMeasure` field in the Azure API response. The `_normalize_rate()` method handles `"1 Token"`, `"1K Tokens"`, and `"1M Tokens"`. A new UoM format may need support.

### Service name changed
Azure may rebrand again. Update `API_SERVICE_NAMES` in `price_resolver.py`. The tuple is tried in order; add the new name first.

### Cache not warming on startup
Check that the `@app.on_event("startup")` handler in `server.py` is executing. Review logs for `pricing_cache_warmup` and `pricing_background_warmup` entries.
