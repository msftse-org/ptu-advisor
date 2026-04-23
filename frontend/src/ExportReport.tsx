import { useCallback, useRef, useState } from 'react'
import type { AnalysisResponse, ConsolidationSummary } from './types'
import './export-report.css'

interface ExportReportProps {
  analysis: AnalysisResponse
  baseAnalysis: AnalysisResponse | null
  isZoomed: boolean
  consolidationSummary?: ConsolidationSummary | null
}

/* ── Formatting helpers ── */

function fmtNumber(value: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value)
}

function fmtCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

function fmtPct(value: number, decimals = 1): string {
  return `${value.toFixed(decimals)}%`
}

/* ── Recommendation display mapping ── */

const RECOMMENDATION_MAP: Record<string, { label: string; icon: string; className: string }> = {
  ptu_recommended: { label: 'PTU Recommended', icon: '✅', className: 'report-rec--green' },
  borderline: { label: 'Borderline — Further Analysis Suggested', icon: '⚠️', className: 'report-rec--amber' },
  ptu_not_recommended: { label: 'PTU Not Recommended — Stay on PAYG', icon: 'ℹ️', className: 'report-rec--blue' },
}

function getRecDisplay(recommendation: string) {
  const key = recommendation.toLowerCase()
  return RECOMMENDATION_MAP[key] ?? { label: recommendation, icon: '•', className: 'report-rec--blue' }
}

/* ── Next steps templates ── */

function buildNextSteps(analysis: AnalysisResponse): string[] {
  const { recommendation, cost_analysis } = analysis
  const rec = recommendation.toLowerCase()
  const ptu = cost_analysis.hybrid.baseline_ptu
  const deployType = cost_analysis.pricing.deployment_type_label
  const resType = cost_analysis.pricing.reservation_type

  if (rec === 'ptu_recommended') {
    return [
      `Reserve ${ptu} PTU (${deployType}, ${resType}).`,
      'Monitor spillover percentage during the first week.',
      'Re-evaluate in 30 days with updated usage data.',
    ]
  }
  if (rec === 'borderline') {
    return [
      'Run a 1-week load test with PTU to validate projected spillover.',
      'Compare actual cost against PAYG baseline.',
      'Re-run this analysis after the test to confirm the recommendation.',
    ]
  }
  return [
    'Stay on PAYG — current usage does not justify provisioned capacity.',
    'Set up Azure cost alerts at the current monthly spend level.',
    'Re-evaluate if traffic grows significantly or throttling appears.',
  ]
}

/* ── Inline SVG chart builders ── */

const SVG_W = 720
const SVG_H = 180
const PAD = { top: 20, right: 16, bottom: 32, left: 60 }
const PLOT_W = SVG_W - PAD.left - PAD.right
const PLOT_H = SVG_H - PAD.top - PAD.bottom

function fmtAxisVal(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`
  return `${Math.round(v)}`
}

function fmtShortDate(iso: string): string {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

/** Build scale helpers from domain to pixel range. */
function makeScale(domain: [number, number], range: [number, number]) {
  const [d0, d1] = domain
  const [r0, r1] = range
  const span = d1 - d0 || 1
  return (v: number) => r0 + ((v - d0) / span) * (r1 - r0)
}

/** Generate ~5 nice round Y-axis tick values. */
function niceYTicks(min: number, max: number): number[] {
  if (max <= min) return [0]
  const range = max - min
  const rough = range / 5
  const mag = Math.pow(10, Math.floor(Math.log10(rough)))
  let step = mag
  if (rough / mag >= 5) step = mag * 5
  else if (rough / mag >= 2) step = mag * 2
  const start = Math.floor(min / step) * step
  const ticks: number[] = []
  for (let v = start; v <= max + step * 0.01; v += step) {
    ticks.push(v)
  }
  return ticks
}

/** Pick ~6 evenly spaced X-axis label indices. */
function pickXLabels(count: number, maxLabels = 6): number[] {
  if (count <= maxLabels) return Array.from({ length: count }, (_, i) => i)
  const step = Math.ceil(count / maxLabels)
  const indices: number[] = []
  for (let i = 0; i < count; i += step) indices.push(i)
  if (indices[indices.length - 1] !== count - 1) indices.push(count - 1)
  return indices
}

/** Polyline path from arrays. */
function polyline(xs: number[], ys: number[]): string {
  return xs.map((x, i) => `${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ')
}

/** TPM over time chart with average reference line. */
function TpmChart({ charts }: { charts: AnalysisResponse['charts'] }) {
  const { timestamps, values, avg } = charts.tpm
  if (!timestamps.length || !values.length) return null

  const yMax = Math.max(...values) * 1.08
  const xScale = makeScale([0, timestamps.length - 1], [PAD.left, PAD.left + PLOT_W])
  const yScale = makeScale([0, yMax], [PAD.top + PLOT_H, PAD.top])

  const pxX = values.map((_, i) => xScale(i))
  const pxY = values.map(v => yScale(v))
  const avgY = yScale(avg)

  const yTicks = niceYTicks(0, yMax)
  const xLabels = pickXLabels(timestamps.length)

  // area fill
  const areaPath = `M${pxX[0].toFixed(1)},${(PAD.top + PLOT_H).toFixed(1)} ${pxX.map((x, i) => `L${x.toFixed(1)},${pxY[i].toFixed(1)}`).join(' ')} L${pxX[pxX.length - 1].toFixed(1)},${(PAD.top + PLOT_H).toFixed(1)} Z`

  return (
    <div className="report-chart">
      <h3 className="report-chart-title">Throughput Over Time (TPM)</h3>
      <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} xmlns="http://www.w3.org/2000/svg" className="report-chart-svg">
        {/* grid lines */}
        {yTicks.map(t => (
          <g key={t}>
            <line x1={PAD.left} x2={PAD.left + PLOT_W} y1={yScale(t)} y2={yScale(t)} stroke="#e8e8e8" />
            <text x={PAD.left - 6} y={yScale(t) + 3} textAnchor="end" fontSize="10" fill="#605e5c">{fmtAxisVal(t)}</text>
          </g>
        ))}
        {/* area */}
        <path d={areaPath} fill="#0078d4" opacity="0.1" />
        {/* TPM line */}
        <polyline points={polyline(pxX, pxY)} fill="none" stroke="#0078d4" strokeWidth="1.5" />
        {/* avg reference */}
        <line x1={PAD.left} x2={PAD.left + PLOT_W} y1={avgY} y2={avgY} stroke="#107c10" strokeDasharray="5 3" strokeWidth="1" />
        <text x={PAD.left + PLOT_W + 2} y={avgY + 3} fontSize="9" fill="#107c10">Avg</text>
        {/* X labels */}
        {xLabels.map(i => (
          <text key={i} x={xScale(i)} y={PAD.top + PLOT_H + 16} textAnchor="middle" fontSize="10" fill="#605e5c">{fmtShortDate(timestamps[i])}</text>
        ))}
        {/* Y axis label */}
        <text x={12} y={PAD.top + PLOT_H / 2} textAnchor="middle" fontSize="10" fill="#605e5c" transform={`rotate(-90, 12, ${PAD.top + PLOT_H / 2})`}>TPM</text>
      </svg>
    </div>
  )
}

/** Cost curve chart: PAYG vs PTU+Spillover with break-even (v2: fixed PTU, varying traffic). */
function CostCurveChart({ charts }: { charts: AnalysisResponse['charts'] }) {
  const cc = charts.cost_curves
  if (!cc.sustained_tpm.length) return null

  const xMin = Math.min(...cc.sustained_tpm)
  const xMax = Math.max(...cc.sustained_tpm)
  const allY = [...cc.payg_monthly, ...cc.ptu_spill_monthly]
  const yMax = Math.max(...allY) * 1.08

  const xScale = makeScale([xMin, xMax], [PAD.left, PAD.left + PLOT_W])
  const yScale = makeScale([0, yMax], [PAD.top + PLOT_H, PAD.top])

  const paygPx = cc.sustained_tpm.map(v => xScale(v))
  const paygPy = cc.payg_monthly.map(v => yScale(v))
  const hybPx = paygPx
  const hybPy = cc.ptu_spill_monthly.map(v => yScale(v))

  const yTicks = niceYTicks(0, yMax)
  const xLabels = pickXLabels(cc.sustained_tpm.length)

  const beX = cc.break_even_tpm != null ? xScale(cc.break_even_tpm) : null
  const avgX = cc.avg_tpm > 0 ? xScale(cc.avg_tpm) : null
  const capX = xScale(cc.ptu_capacity_tpm)

  return (
    <div className="report-chart">
      <h3 className="report-chart-title">Cost Explorer — Does traffic justify {cc.selected_ptu} PTU?</h3>
      <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} xmlns="http://www.w3.org/2000/svg" className="report-chart-svg">
        {yTicks.map(t => (
          <g key={t}>
            <line x1={PAD.left} x2={PAD.left + PLOT_W} y1={yScale(t)} y2={yScale(t)} stroke="#e8e8e8" />
            <text x={PAD.left - 6} y={yScale(t) + 3} textAnchor="end" fontSize="10" fill="#605e5c">${fmtAxisVal(t)}</text>
          </g>
        ))}
        {/* break-even vertical */}
        {beX != null && (
          <>
            <line x1={beX} x2={beX} y1={PAD.top} y2={PAD.top + PLOT_H} stroke="#d83b01" strokeDasharray="5 3" strokeWidth="1" />
            <text x={beX} y={PAD.top - 4} textAnchor="middle" fontSize="9" fill="#d83b01">Break-even</text>
          </>
        )}
        {/* PTU capacity vertical (inflection point) */}
        <line x1={capX} x2={capX} y1={PAD.top} y2={PAD.top + PLOT_H} stroke="#107c10" strokeDasharray="2 2" strokeWidth="1" />
        <text x={capX} y={PAD.top + PLOT_H + 26} textAnchor="middle" fontSize="9" fill="#107c10">{cc.selected_ptu} PTU capacity</text>
        {/* Your avg TPM vertical */}
        {avgX != null && (
          <>
            <line x1={avgX} x2={avgX} y1={PAD.top} y2={PAD.top + PLOT_H} stroke="#8b5cf6" strokeDasharray="4 2" strokeWidth="1" />
            <text x={avgX} y={PAD.top - 4} textAnchor="middle" fontSize="9" fill="#8b5cf6">Your avg TPM</text>
          </>
        )}
        {/* PAYG line */}
        <polyline points={polyline(paygPx, paygPy)} fill="none" stroke="#0078d4" strokeWidth="1.5" strokeDasharray="5 4" />
        {/* Hybrid line */}
        <polyline points={polyline(hybPx, hybPy)} fill="none" stroke="#107c10" strokeWidth="1.5" />
        {/* X labels */}
        {xLabels.map(i => (
          <text key={i} x={xScale(cc.sustained_tpm[i])} y={PAD.top + PLOT_H + 16} textAnchor="middle" fontSize="10" fill="#605e5c">{fmtAxisVal(cc.sustained_tpm[i])}</text>
        ))}
        {/* legend */}
        <line x1={PAD.left + 8} x2={PAD.left + 28} y1={PAD.top + 6} y2={PAD.top + 6} stroke="#0078d4" strokeDasharray="5 4" strokeWidth="1.5" />
        <text x={PAD.left + 32} y={PAD.top + 10} fontSize="10" fill="#605e5c">PAYG</text>
        <line x1={PAD.left + 78} x2={PAD.left + 98} y1={PAD.top + 6} y2={PAD.top + 6} stroke="#107c10" strokeWidth="1.5" />
        <text x={PAD.left + 102} y={PAD.top + 10} fontSize="10" fill="#605e5c">PTU + Spillover</text>
        {/* X axis label */}
        <text x={PAD.left + PLOT_W / 2} y={PAD.top + PLOT_H + 36} textAnchor="middle" fontSize="10" fill="#605e5c">Sustained TPM</text>
        {/* Y axis label */}
        <text x={12} y={PAD.top + PLOT_H / 2} textAnchor="middle" fontSize="10" fill="#605e5c" transform={`rotate(-90, 12, ${PAD.top + PLOT_H / 2})`}>$/month</text>
      </svg>
    </div>
  )
}

/** Throttle rate chart — only rendered when throttling data has non-zero values. */
function ThrottleChart({ charts }: { charts: AnalysisResponse['charts'] }) {
  const { timestamps, values } = charts.throttling
  if (!timestamps.length || !values.length) return null
  const hasThrottling = values.some(v => v > 0)
  if (!hasThrottling) return null

  const yMax = Math.max(...values) * 1.15 || 1
  const xScale = makeScale([0, timestamps.length - 1], [PAD.left, PAD.left + PLOT_W])
  const yScale = makeScale([0, yMax], [PAD.top + PLOT_H, PAD.top])

  const pxX = values.map((_, i) => xScale(i))
  const pxY = values.map(v => yScale(v))

  const areaPath = `M${pxX[0].toFixed(1)},${(PAD.top + PLOT_H).toFixed(1)} ${pxX.map((x, i) => `L${x.toFixed(1)},${pxY[i].toFixed(1)}`).join(' ')} L${pxX[pxX.length - 1].toFixed(1)},${(PAD.top + PLOT_H).toFixed(1)} Z`

  const yTicks = niceYTicks(0, yMax)
  const xLabels = pickXLabels(timestamps.length)

  return (
    <div className="report-chart">
      <h3 className="report-chart-title">Rate-Limit Events (HTTP 429)</h3>
      <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} xmlns="http://www.w3.org/2000/svg" className="report-chart-svg">
        {yTicks.map(t => (
          <g key={t}>
            <line x1={PAD.left} x2={PAD.left + PLOT_W} y1={yScale(t)} y2={yScale(t)} stroke="#e8e8e8" />
            <text x={PAD.left - 6} y={yScale(t) + 3} textAnchor="end" fontSize="10" fill="#605e5c">{fmtAxisVal(t)}</text>
          </g>
        ))}
        <path d={areaPath} fill="#d83b01" opacity="0.1" />
        <polyline points={polyline(pxX, pxY)} fill="none" stroke="#d83b01" strokeWidth="1.5" />
        {xLabels.map(i => (
          <text key={i} x={xScale(i)} y={PAD.top + PLOT_H + 16} textAnchor="middle" fontSize="10" fill="#605e5c">{fmtShortDate(timestamps[i])}</text>
        ))}
        <text x={12} y={PAD.top + PLOT_H / 2} textAnchor="middle" fontSize="10" fill="#605e5c" transform={`rotate(-90, 12, ${PAD.top + PLOT_H / 2})`}>429 Events</text>
      </svg>
    </div>
  )
}

/* ── The static report markup ── */

function ReportContent({ analysis, baseAnalysis, isZoomed, consolidationSummary }: ExportReportProps) {
  const rec = getRecDisplay(analysis.recommendation)
  const m = analysis.metrics
  const cost = analysis.cost_analysis
  const nextSteps = buildNextSteps(analysis)
  const now = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
  const isConsolidated = consolidationSummary != null

  return (
    <div className="export-report" id="export-report-root">
      {/* Header */}
      <header className="report-header">
        <h1 className="report-title">
          PTU Advisor — {isConsolidated ? 'Consolidation Assessment' : 'Deployment Assessment'}
        </h1>
        <div className="report-meta">
          {isConsolidated ? (
            <>
              <span><strong>Analysis Mode:</strong> Consolidation ({consolidationSummary.deployment_count} deployments)</span>
              <span><strong>Model:</strong> {consolidationSummary.model_name}</span>
              <span><strong>Deployments:</strong> {consolidationSummary.individual_deployments.map(d => d.name).join(', ')}</span>
            </>
          ) : (
            <>
              <span><strong>Deployment:</strong> {m.deployment_name}</span>
              <span><strong>Model:</strong> {m.model_name}</span>
            </>
          )}
          <span>
            <strong>Analysis Period:</strong> {analysis.analysis_period}
            {isZoomed && ' (zoomed)'}
          </span>
          {isZoomed && baseAnalysis && (
            <span><strong>Full Lookback:</strong> {baseAnalysis.analysis_period}</span>
          )}
          <span><strong>Generated:</strong> {now}</span>
        </div>
      </header>

      {/* 1 — Recommendation */}
      <section className="report-section">
        <h2 className="report-section-title">1. Recommendation</h2>
        <div className={`report-rec-banner ${rec.className}`}>
          <span className="report-rec-icon">{rec.icon}</span>
          <div>
            <strong>{rec.label}</strong>
            <span className="report-rec-confidence"> · Confidence: {fmtPct(analysis.confidence * 100)}</span>
          </div>
        </div>
        <p className="report-summary">{analysis.summary}</p>
      </section>

      {/* Consolidation Summary (only in consolidation mode) */}
      {isConsolidated && (
        <section className="report-section">
          <h2 className="report-section-title">2. Consolidation Summary</h2>
          <p className="report-text" style={{ marginBottom: 8 }}>
            {consolidationSummary.all_on_ptu
              ? `All ${consolidationSummary.deployment_count} deployments already use PTU. ${
                  consolidationSummary.savings > 0
                    ? `Consolidating onto a single PTU allocation saves an estimated ${fmtCurrency(consolidationSummary.savings)}/month (${fmtPct(consolidationSummary.savings_pct)}) vs the current combined PTU spend.`
                    : `The current separate PTU allocations are already cost-effective. Consolidation would cost ${fmtCurrency(Math.abs(consolidationSummary.savings))}/month more.`
                }`
              : consolidationSummary.savings > 0
                ? `Consolidating these ${consolidationSummary.deployment_count} deployments onto shared PTU capacity saves an estimated ${fmtCurrency(consolidationSummary.savings)}/month (${fmtPct(consolidationSummary.savings_pct)}).`
                : `Consolidation does not save money. Individual PAYG is more cost-effective by ${fmtCurrency(Math.abs(consolidationSummary.savings))}/month.`
            }
          </p>
          {consolidationSummary.warnings.length > 0 && (
            <div className="report-consolidation-warnings" data-testid="report-consolidation-warnings">
              {consolidationSummary.warnings.map((w, i) => (
                <p key={i} className="report-warning-item">{w}</p>
              ))}
            </div>
          )}
          <table className="report-consolidation-table">
            <thead>
              <tr>
                <th>Deployment</th>
                <th style={{ textAlign: 'right' }}>Avg TPM</th>
                <th style={{ textAlign: 'right' }}>Peak TPM</th>
                <th style={{ textAlign: 'right' }}>Throttle %</th>
                <th style={{ textAlign: 'right' }}>PAYG Cost</th>
              </tr>
            </thead>
            <tbody>
              {consolidationSummary.individual_deployments.map(dep => (
                <tr key={dep.name}>
                  <td>{dep.name}</td>
                  <td style={{ textAlign: 'right' }}>{fmtNumber(dep.avg_tpm)}</td>
                  <td style={{ textAlign: 'right' }}>{fmtNumber(dep.peak_tpm)}</td>
                  <td style={{ textAlign: 'right' }}>{fmtPct(dep.throttling_rate_pct)}</td>
                  <td style={{ textAlign: 'right' }}>{fmtCurrency(dep.payg_monthly_cost)}</td>
                </tr>
              ))}
              <tr className="consolidation-total-row">
                <td><strong>Combined</strong></td>
                <td style={{ textAlign: 'right' }}><strong>{fmtNumber(consolidationSummary.combined_avg_tpm)}</strong></td>
                <td style={{ textAlign: 'right' }}><strong>{fmtNumber(consolidationSummary.combined_peak_tpm)}</strong></td>
                <td style={{ textAlign: 'right' }}><strong>{fmtPct(consolidationSummary.combined_throttling_rate_pct)}</strong></td>
                <td style={{ textAlign: 'right' }}><strong>{fmtCurrency(consolidationSummary.individual_payg_total)}</strong></td>
              </tr>
            </tbody>
          </table>
          <table className="report-cost-table" style={{ marginTop: 12 }}>
            <tbody>
              <tr>
                <td className="cost-label">Sum of Individual PAYG</td>
                <td className="cost-value">{fmtCurrency(consolidationSummary.individual_payg_total)} / month</td>
              </tr>
              <tr>
                <td className="cost-label">Consolidated PTU + Spillover</td>
                <td className="cost-value">{fmtCurrency(consolidationSummary.consolidated_hybrid_cost)} / month</td>
              </tr>
              <tr className="cost-highlight">
                <td className="cost-label">Monthly Savings</td>
                <td className="cost-value">
                  {consolidationSummary.savings > 0 ? '-' : '+'}{fmtCurrency(Math.abs(consolidationSummary.savings))} ({fmtPct(Math.abs(consolidationSummary.savings_pct))})
                </td>
              </tr>
            </tbody>
          </table>
        </section>
      )}

      {/* Key Evidence (section number adjusts for consolidation) */}
      <section className="report-section">
        <h2 className="report-section-title">{isConsolidated ? '3' : '2'}. Key Evidence{isConsolidated ? ' (Combined Metrics)' : ''}</h2>
        <table className="report-metrics-table">
          <tbody>
            <tr><td className="metric-label">Average TPM</td><td className="metric-value">{fmtNumber(m.avg_tpm)}</td></tr>
            <tr><td className="metric-label">Peak TPM</td><td className="metric-value">{fmtNumber(m.peak_tpm)}</td></tr>
            <tr><td className="metric-label">Throttle Rate</td><td className="metric-value">{fmtPct(m.throttling_rate_pct)}</td></tr>
            <tr><td className="metric-label">P95 Latency</td><td className="metric-value">{Math.round(m.latency.p95)} ms</td></tr>
            <tr><td className="metric-label">Active Hours</td><td className="metric-value">{fmtPct(m.utilization.active_hours_percentage)}</td></tr>
            <tr><td className="metric-label">Burstiness (peak / avg)</td><td className="metric-value">{m.utilization.peak_to_average_ratio.toFixed(2)}x</td></tr>
          </tbody>
        </table>
        <TpmChart charts={analysis.charts} />
        <ThrottleChart charts={analysis.charts} />
      </section>

      {/* Cost Comparison */}
      <section className="report-section">
        <h2 className="report-section-title">{isConsolidated ? '4' : '3'}. Cost Comparison</h2>
        <table className="report-cost-table">
          <tbody>
            <tr>
              <td className="cost-label">PAYG Only</td>
              <td className="cost-value">{fmtCurrency(cost.payg.payg_total)} / month</td>
            </tr>
            <tr>
              <td className="cost-label">PTU + Spillover</td>
              <td className="cost-value">{fmtCurrency(cost.hybrid.hybrid_total)} / month</td>
            </tr>
            <tr className="cost-highlight">
              <td className="cost-label">Monthly Savings</td>
              <td className="cost-value">
                {fmtCurrency(cost.comparison.savings)} ({fmtPct(cost.comparison.savings_pct)})
              </td>
            </tr>
            {cost.comparison.break_even_tpm != null && (
              <tr>
                <td className="cost-label">Break-even TPM</td>
                <td className="cost-value">{fmtNumber(cost.comparison.break_even_tpm)}</td>
              </tr>
            )}
          </tbody>
        </table>
        <p className="report-assumptions">
          {cost.pricing.reservation_type} · {cost.pricing.region_display_name} ({cost.pricing.region_multiplier}x) · {cost.pricing.deployment_type_label} · {cost.hybrid.baseline_ptu} PTU baseline
        </p>
        <CostCurveChart charts={analysis.charts} />
      </section>

      {/* Why This Recommendation */}
      <section className="report-section">
        <h2 className="report-section-title">{isConsolidated ? '5' : '4'}. Why This Recommendation</h2>
        <p className="report-text">{analysis.explanation}</p>
        <ul className="report-dimensions">
          {analysis.dimensions
            .filter(d => d.score !== 'INSUFFICIENT')
            .map(d => (
              <li key={d.name}><strong>{d.name}:</strong> {d.summary}</li>
            ))
          }
        </ul>
      </section>

      {/* What Would Change This */}
      <section className="report-section">
        <h2 className="report-section-title">{isConsolidated ? '6' : '5'}. What Would Change This</h2>
        <p className="report-text">{analysis.what_would_change}</p>
      </section>

      {/* Next Steps */}
      <section className="report-section">
        <h2 className="report-section-title">{isConsolidated ? '7' : '6'}. Recommended Next Steps</h2>
        <ol className="report-next-steps">
          {nextSteps.map((step, i) => <li key={i}>{step}</li>)}
        </ol>
      </section>

      {/* Footer */}
      <footer className="report-footer">
        Generated by PTU Advisor · {now} · For discussion purposes only — not a contractual commitment.
      </footer>
    </div>
  )
}

/* ── Inline CSS for the self-contained HTML download ── */

const REPORT_INLINE_CSS = `
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #fff; color: #323130; font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif; }
  .export-report { max-width: 800px; margin: 0 auto; padding: 40px; }
  .report-header { border-bottom: 2px solid #0078d4; padding-bottom: 16px; margin-bottom: 24px; }
  .report-title { font-size: 20px; font-weight: 600; color: #0078d4; margin-bottom: 8px; }
  .report-meta { display: flex; flex-direction: column; gap: 2px; font-size: 13px; color: #605e5c; }
  .report-section { margin-bottom: 24px; }
  .report-section-title { font-size: 16px; font-weight: 600; color: #323130; margin-bottom: 8px; border-bottom: 1px solid #edebe9; padding-bottom: 4px; }
  .report-rec-banner { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-radius: 6px; font-size: 14px; margin-bottom: 10px; }
  .report-rec--green { background: #dff6dd; color: #107c10; }
  .report-rec--amber { background: #fff4ce; color: #7a6400; }
  .report-rec--blue { background: #deecf9; color: #0078d4; }
  .report-rec-icon { font-size: 18px; }
  .report-rec-confidence { font-weight: 400; opacity: 0.85; }
  .report-summary { font-size: 13px; line-height: 1.6; color: #323130; }
  .report-metrics-table, .report-cost-table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
  .report-metrics-table td, .report-cost-table td { padding: 6px 12px; font-size: 13px; border-bottom: 1px solid #f3f2f1; }
  .metric-label, .cost-label { color: #605e5c; }
  .metric-value, .cost-value { font-weight: 600; text-align: right; }
  .cost-highlight td { font-weight: 600; color: #107c10; }
  .report-assumptions { font-size: 11px; color: #a19f9d; margin-top: 4px; }
  .report-text { font-size: 13px; line-height: 1.6; color: #323130; white-space: pre-line; }
  .report-dimensions { margin-top: 8px; padding-left: 20px; font-size: 13px; line-height: 1.6; }
  .report-next-steps { padding-left: 20px; font-size: 13px; line-height: 1.8; }
  .report-footer { margin-top: 32px; padding-top: 12px; border-top: 1px solid #edebe9; font-size: 11px; color: #a19f9d; text-align: center; }
  .report-chart { margin-top: 16px; }
  .report-chart-title { font-size: 13px; font-weight: 600; color: #323130; margin-bottom: 6px; }
  .report-chart-svg { width: 100%; height: auto; display: block; }
  .report-consolidation-table { width: 100%; border-collapse: collapse; margin-bottom: 8px; font-size: 13px; }
  .report-consolidation-table th { text-align: left; padding: 6px 12px; border-bottom: 2px solid #edebe9; color: #605e5c; font-weight: 600; font-size: 12px; }
  .report-consolidation-table td { padding: 6px 12px; border-bottom: 1px solid #f3f2f1; }
  .consolidation-total-row td { border-top: 2px solid #edebe9; background: #faf9f8; }
  .report-consolidation-warnings { margin-bottom: 10px; }
  .report-warning-item { margin: 0 0 4px 0; padding: 6px 10px; background: #fff8e1; border-left: 3px solid #d4a017; font-size: 12px; line-height: 1.5; color: #7a6520; }
`

/* ── Export logic ── */

function buildReportHTML(reportEl: HTMLElement): string {
  const isConsolidation = reportEl.querySelector('.report-consolidation-table') != null
  const title = isConsolidation ? 'PTU Advisor — Consolidation Assessment' : 'PTU Advisor — Deployment Assessment'
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${title}</title>
  <style>${REPORT_INLINE_CSS}</style>
</head>
<body>
  ${reportEl.innerHTML}
</body>
</html>`
}

function downloadBlob(html: string, filename: string) {
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function printReport(reportEl: HTMLElement) {
  const printWindow = window.open('', '_blank', 'width=900,height=700')
  if (!printWindow) return
  const html = buildReportHTML(reportEl)
  printWindow.document.open()
  printWindow.document.write(html)
  printWindow.document.close()
  // Allow browser to parse & render before triggering print
  setTimeout(() => {
    printWindow.focus()
    printWindow.print()
  }, 400)
}

/* ── Public component ── */

export function ExportReport({ analysis, baseAnalysis, isZoomed, consolidationSummary }: ExportReportProps) {
  const reportRef = useRef<HTMLDivElement>(null)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const isConsolidated = consolidationSummary != null

  const handlePDF = useCallback(() => {
    setDropdownOpen(false)
    if (reportRef.current) printReport(reportRef.current)
  }, [])

  const handleHTML = useCallback(() => {
    setDropdownOpen(false)
    if (!reportRef.current) return
    const html = buildReportHTML(reportRef.current)
    const prefix = isConsolidated ? 'ptu-consolidation' : 'ptu-assessment'
    const suffix = isConsolidated
      ? `${consolidationSummary.model_name}-${consolidationSummary.deployment_count}deps`
      : analysis.metrics.deployment_name
    const name = `${prefix}-${suffix}-${new Date().toISOString().slice(0, 10)}.html`
    downloadBlob(html, name)
  }, [analysis.metrics.deployment_name, isConsolidated, consolidationSummary])

  return (
    <>
      {/* Export dropdown button */}
      <div className="export-dropdown" data-testid="export-dropdown">
        <button
          className="export-btn"
          onClick={() => setDropdownOpen(v => !v)}
          aria-haspopup="true"
          aria-expanded={dropdownOpen}
        >
          Export Report ▾
        </button>
        {dropdownOpen && (
          <ul className="export-menu" role="menu">
            <li role="menuitem"><button onClick={handlePDF}>Download PDF</button></li>
            <li role="menuitem"><button onClick={handleHTML}>Download HTML</button></li>
          </ul>
        )}
      </div>

      {/* Hidden report content (used as source for export) */}
      <div ref={reportRef} style={{ position: 'absolute', left: '-9999px', top: 0 }} aria-hidden="true">
        <ReportContent analysis={analysis} baseAnalysis={baseAnalysis} isZoomed={isZoomed} consolidationSummary={consolidationSummary} />
      </div>
    </>
  )
}
