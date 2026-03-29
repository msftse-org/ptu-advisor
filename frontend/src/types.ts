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
  sku_type: string
  sku_capacity: number | null
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
    cost_curves: {
      sustained_tpm: number[]
      payg_monthly: number[]
      ptu_spill_monthly: number[]
      break_even_tpm: number | null
      break_even_reason: 'exists' | 'ptu_always_more_expensive' | 'ptu_always_cheaper'
      ptu_capacity_tpm: number
      avg_tpm: number
      selected_ptu: number
      payg_at_avg: number
      hybrid_at_avg: number
    }
  }
  cost_analysis: {
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
      payg_output_rate_per_million: number
      output_ratio: number
      ptu_hourly_rate: number
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
      cheaper_strategy: string
    }
    commitment_safety: {
      savings_margin_pct: number
      spillover_pct: number
      capacity_coverage_pct: number
      safety_verdict: 'safe' | 'efficient_but_risky' | 'not_justified'
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
