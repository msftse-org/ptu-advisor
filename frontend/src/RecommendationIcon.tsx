export type RecommendationIconKind = 'recommended' | 'borderline' | 'info' | 'insufficient'

interface RecommendationIconProps {
  kind: RecommendationIconKind
  className?: string
}

export function RecommendationIcon({ kind, className }: RecommendationIconProps) {
  return (
    <svg
      className={className}
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      data-recommendation-icon={kind}
      xmlns="http://www.w3.org/2000/svg"
    >
      {kind === 'recommended' && (
        <>
          <circle cx="8" cy="8" r="6" />
          <path d="m5 8 2 2 4-4" />
        </>
      )}
      {kind === 'borderline' && (
        <>
          <path d="M8 1.75 14.25 13H1.75L8 1.75Z" />
          <path d="M8 5.5v3.25" />
          <circle cx="8" cy="11.25" r="0.45" fill="currentColor" stroke="none" />
        </>
      )}
      {kind === 'info' && (
        <>
          <circle cx="8" cy="8" r="6" />
          <path d="M8 7.25v4" />
          <circle cx="8" cy="4.75" r="0.45" fill="currentColor" stroke="none" />
        </>
      )}
      {kind === 'insufficient' && (
        <>
          <ellipse cx="8" cy="3.5" rx="5.5" ry="2" />
          <path d="M2.5 3.5v4c0 1.1 2.46 2 5.5 2s5.5-.9 5.5-2v-4" />
          <path d="M2.5 7.5V11c0 1.1 2.46 2 5.5 2 1.16 0 2.24-.13 3.12-.37" />
          <path d="M10.5 10.5h3" />
        </>
      )}
    </svg>
  )
}