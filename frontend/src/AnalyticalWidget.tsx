import { useId, useState, type ReactNode } from 'react'

type SemanticStatus = {
  label: string
  tone: 'positive' | 'warning' | 'negative' | 'neutral'
}

type AnalyticalWidgetProps = {
  title: string
  ariaLabel?: string
  headline: ReactNode
  metricLabel: string
  context?: ReactNode
  status?: SemanticStatus
  summary: string
  tooltip: ReactNode
  helpContent?: string
  onExpand?: () => void
  expanded?: boolean
  className?: string
  children: ReactNode
}

export function AnalyticalWidget({
  title,
  ariaLabel,
  headline,
  metricLabel,
  context,
  status,
  summary,
  tooltip,
  helpContent,
  onExpand,
  expanded = false,
  className = '',
  children,
}: AnalyticalWidgetProps) {
  const summaryId = useId()
  const [showHelp, setShowHelp] = useState(false)
  const classes = ['chart-card', 'analytical-widget', className].filter(Boolean).join(' ')

  return (
    <article
      className={classes}
      role="region"
      aria-label={ariaLabel ?? `${title} analytical widget`}
      aria-describedby={summaryId}
    >
      <div className="analytical-widget-heading">
        <h4 className="widget-header" aria-label={`Hover to inspect exact values for ${title}`}>
          <span>{title}</span>
          <span className="widget-header-actions">
            {helpContent && (
              <button
                className="chart-help-btn"
                onClick={() => setShowHelp((current) => !current)}
                aria-label="Help: hybrid model explanation"
                aria-expanded={showHelp}
                title="How the hybrid model works"
              >
                ?
              </button>
            )}
            {onExpand && (
              <button
                className="chart-expand-btn"
                onClick={onExpand}
                aria-label={`${expanded ? 'Collapse' : 'Expand'} ${title}`}
                aria-pressed={expanded}
                title={`${expanded ? 'Collapse' : 'Expand'} chart`}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M1 5V1h4M9 1h4v4M13 9v4H9M5 13H1V9" />
                </svg>
              </button>
            )}
            {tooltip}
          </span>
        </h4>
        <div className="analytical-widget-kpi-row">
          <div className="analytical-widget-kpi">
            <strong>{headline}</strong>
            <span>{metricLabel}</span>
          </div>
          {context && <div className="analytical-widget-context">{context}</div>}
          {status && (
            <span className={`analytical-widget-status status-${status.tone}`} role="status">
              {status.label}
            </span>
          )}
        </div>
      </div>
      <p className="visually-hidden" id={summaryId}>{summary}</p>
      {helpContent && showHelp && (
        <div className="hybrid-help-panel" role="region" aria-label="Hybrid model explanation">
          <p>{helpContent}</p>
        </div>
      )}
      <div className="analytical-widget-body">{children}</div>
    </article>
  )
}