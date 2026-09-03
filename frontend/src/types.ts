export type AuthStatus = {
  authenticated: boolean
  display_name: string
  email: string
  tenant_id: string
  error?: string
}

export type FocusTopic = {
  name: string
  tagline: string
}

export type PricingRegion = {
  name: string
  display_name: string
  multiplier: number
  zone: string
}

export type DeploymentTypeOption = {
  name: 'global' | 'data_zone' | 'regional'
  label: string
  increment: number
  default_min_ptu: number
  base_hourly_rate: number
}

/** Lightweight pre-analysis stats for a single deployment (from GET /api/deployments/preview). */
export type DeploymentPreview = {
  name: string
  avg_tpm: number
  throttling_rate_pct: number
}

export type PricingOptions = {
  regions: PricingRegion[]
  deployment_types: DeploymentTypeOption[]
}

export type SubscriptionInfo = {
  subscription_id: string
  display_name: string
  state: string
  label: string
}

export type AccountInfo = {
  name: string
  resource_group: string
  location: string
  kind: string
  sku_name: string
  label: string
}

export type DeploymentInfo = {
  name: string
  model: string
  model_version?: string | null
  model_family: string
  sku_type: string
  sku_capacity: number | null
  ptu_eligible: boolean
  ineligibility_reason?: string
}

export type DimensionResult = {
  name: string
  score: string
  confidence: number
  summary: string
  explanation: string
  key_metrics: Record<string, number>
  is_positive: boolean
}

export type AnalysisResponse = {
  recommendation: string
  confidence: number
  summary: string
  explanation: string
  what_would_change: string
  data_quality: string
  analysis_period: string
  dimensions: DimensionResult[]
  metrics: {
    deployment_name: string
    model_name: string
    avg_tpm: number
    peak_tpm: number
    throttling_rate_pct: number
    total_requests: number
    throttled_requests: number
    successful_requests: number
    total_tokens: number
    total_tokens_millions: number
    lookback_days: number
    latency: {
      p50: number
      p95: number
      p99: number
    }
    cache_match_rate?: {
      avg_pct: number
      p95_pct: number
      available: boolean
      source: 'observed' | 'inferred' | 'mixed' | 'override' | 'disabled' | 'unavailable'
      quality: 'good' | 'partial' | 'limited' | 'unavailable'
      coverage_pct: number
      cached_prompt_tokens: number
      active_prompt_tokens: number
      active_tokens_observed: number
    }
    utilization: {
      peak_to_average_ratio: number
      sustained_utilization_rate: number
      active_hours_percentage: number
      business_hours_concentration: number
      weekend_vs_weekday_ratio: number
    }
  }
  charts: {
    tokens: {
      timestamps: string[]
      prompt: number[]
      completion: number[]
      total: number[]
    }
    requests: {
      timestamps: string[]
      successful: number[]
      throttled: number[]
      total: number[]
    }
    daily_cost: {
      dates: string[]
      input_cost: number[]
      output_cost: number[]
      total_cost: number[]
      avg_daily_cost: number
      ptu_daily_cost: number
    }
    tpm: {
      timestamps: string[]
      values: number[]
      avg: number
      p25: number
      p95: number
    }
    throttling: {
      timestamps: string[]
      values: number[]
    }
    prompt_cache: {
      timestamps: string[]
      match_rate_pct: Array<number | null>
      prompt_tokens: number[]
      cached_prompt_tokens: number[]
      active_prompt_tokens: number[]
      source: 'observed' | 'inferred' | 'mixed' | 'override' | 'disabled' | 'unavailable'
    }
    cost_curves: {
      sustained_tpm: number[]
      payg_monthly: number[]
      ptu_spill_monthly: number[]
      break_even_tpm: number | null
      upper_break_even_tpm?: number | null
      break_even_reason: 'exists' | 'ptu_always_more_expensive' | 'ptu_always_cheaper' | 'insufficient_data'
      ptu_capacity_tpm: number
      avg_tpm: number
      selected_ptu: number
      payg_at_avg: number
      hybrid_at_avg: number
    }
  }
  cost_analysis: {
    status?: 'ready' | 'insufficient_data'
    pricing: {
      focus_topic: string
      reservation_type: string
      reservation_discount_pct: number
      region: string
      region_display_name: string
      region_multiplier: number
      deployment_type: 'global' | 'data_zone' | 'regional'
      deployment_type_label: string
      payg_blended_rate_per_million: number
      payg_input_rate_per_million: number
      payg_cached_input_rate_per_million: number
      cached_input_pricing_source: 'live' | 'cached' | 'fallback' | 'manual' | 'conservative'
      payg_output_rate_per_million: number
      output_ratio: number
      ptu_hourly_rate: number
      ptu_pricing_source?: 'live' | 'cached' | 'fallback' | 'manual'
      ptu_capacity_per_unit: number
      ptu_increment: number
      ptu_minimum: number
      pricing_source: 'live' | 'cached' | 'fallback' | 'manual'
      pricing_as_of: string
      pricing_currency: string
    }
    payg: {
      monthly_tokens: number
      payg_base: number
      throttle_impact: number
      payg_total: number
    }
    hybrid: {
      baseline_percentile: number
      baseline_label: string
      baseline_tpm: number
      baseline_ptu: number
      default_baseline_ptu: number
      max_viable_baseline_ptu: number | null
      max_baseline_ptu: number
      ptu_capacity_tpm: number
      avg_spillover_tpm: number
      spillover_tokens_monthly: number
      spillover_cost: number
      ptu_baseline_cost: number
      hybrid_total: number
      spillover_pct: number
    }
    full_ptu: {
      ptu_needed_full: number
      ptu_monthly_full: number
      ptu_committed_cost: number
    }
    comparison: {
      savings: number
      savings_pct: number
      break_even_tpm: number | null
      upper_break_even_tpm?: number | null
      cheaper_strategy: string | null
    }
    no_cache_comparison?: {
      payg_total: number
      ptu_baseline_cost: number
      spillover_cost: number
      hybrid_total: number
      savings: number
      savings_pct: number
      recommendation: 'ptu_recommended' | 'borderline' | 'ptu_not_recommended' | 'insufficient_data'
      break_even_tpm: number | null
      upper_break_even_tpm?: number | null
      commitment_safety: {
        savings_margin_pct: number
        spillover_pct: number
        capacity_coverage_pct: number
        safety_verdict: 'safe' | 'efficient_but_risky' | 'not_justified' | 'insufficient_data'
      }
    }
    commitment_safety: {
      savings_margin_pct: number
      spillover_pct: number
      capacity_coverage_pct: number
      safety_verdict: 'safe' | 'efficient_but_risky' | 'not_justified' | 'insufficient_data'
    }
    cache_impact: {
      applied: boolean
      source: 'observed' | 'inferred' | 'mixed' | 'override' | 'disabled' | 'unavailable'
      quality: 'good' | 'partial' | 'limited' | 'unavailable'
      coverage_pct: number
      no_cache_normalized_avg_tpm: number
      cache_adjusted_normalized_avg_tpm: number
      normalized_tpm_reduction_pct: number
      no_cache_recommended_ptu: number
      cache_aware_recommended_ptu: number
      ptu_avoided: number
      no_cache_payg_monthly: number
      cache_aware_payg_monthly: number
      payg_cache_savings: number
      fixed_ptu_cost_changed: boolean
      validation_warnings?: string[]
      calculation_note: string
    }
    formula_blocks: {
      payg: string
      hybrid: string
    }
  }
  insights: {
    break_even_message: string
    focus_topic: string
    analysis_notes: string[]
  }
}

// ---------------------------------------------------------------------------
// Consolidation Analysis types
// ---------------------------------------------------------------------------

export type AnalysisMode = 'single' | 'consolidation'

export type IndividualDeploymentSummary = {
  name: string
  avg_tpm: number
  peak_tpm: number
  throttling_rate_pct: number
  total_requests: number
  latency_p50: number
  latency_p95: number
  payg_monthly_cost: number
}

export type ConsolidationSummary = {
  deployment_count: number
  model_name: string
  deployment_type: string
  individual_deployments: IndividualDeploymentSummary[]
  combined_avg_tpm: number
  combined_peak_tpm: number
  combined_throttling_rate_pct: number
  individual_payg_total: number
  consolidated_hybrid_cost: number
  savings: number
  savings_pct: number
  warnings: string[]
  all_on_ptu: boolean
}

// ---------------------------------------------------------------------------
// Per-deployment chart data (Phase 2 — consolidation chart attribution)
// ---------------------------------------------------------------------------

/** Per-deployment token breakdown (prompt + completion per deployment). */
export type PerDeploymentTokens = Record<string, { prompt: number[]; completion: number[] }>

/** Per-deployment request breakdown (successful + throttled per deployment). */
export type PerDeploymentRequests = Record<string, { successful: number[]; throttled: number[] }>

/** Per-deployment latency traces (p50/p95/p99 per deployment — overlaid, not stacked). */
export type PerDeploymentLatency = Record<string, { p50: number[]; p95: number[]; p99: number[] }>

/** Per-deployment TPM values (one array per deployment). */
export type PerDeploymentTpm = Record<string, number[]>

/** Per-deployment throttling (429) event values. */
export type PerDeploymentThrottling = Record<string, number[]>

export type PerDeploymentCache = Record<string, {
  match_rate_pct: Array<number | null>
  cached_prompt_tokens: number[]
  active_prompt_tokens: number[]
  source: 'observed' | 'inferred' | 'mixed' | 'unavailable'
}>

/** Extended charts shape returned by consolidation endpoint. */
export type ConsolidationCharts = AnalysisResponse['charts'] & {
  tokens: AnalysisResponse['charts']['tokens'] & {
    per_deployment: PerDeploymentTokens
  }
  requests: AnalysisResponse['charts']['requests'] & {
    per_deployment: PerDeploymentRequests
  }
  tpm: AnalysisResponse['charts']['tpm'] & {
    per_deployment: PerDeploymentTpm
  }
  throttling: AnalysisResponse['charts']['throttling'] & {
    per_deployment: PerDeploymentThrottling
  }
  prompt_cache: AnalysisResponse['charts']['prompt_cache'] & {
    per_deployment: PerDeploymentCache
  }
  latency: {
    timestamps: string[]
    combined: { p50: number[]; p95: number[]; p99: number[] }
    per_deployment: PerDeploymentLatency
  }
}

export type ConsolidationResponse = Omit<AnalysisResponse, 'charts'> & {
  charts: ConsolidationCharts
  consolidation_summary: ConsolidationSummary
}
