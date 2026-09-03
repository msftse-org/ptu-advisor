export function calculateBreakEvenRange({
  ptuFixed,
  ptuCapacityRaw,
  paygRatePerMillion,
  spilloverRatePerMillion,
}: {
  ptuFixed: number
  ptuCapacityRaw: number
  paygRatePerMillion: number
  spilloverRatePerMillion: number
}): { lower: number | null; upper: number | null } {
  const minutesPerMonth = 43_200
  const paygSlope = paygRatePerMillion * minutesPerMonth / 1_000_000
  const spilloverSlope = spilloverRatePerMillion * minutesPerMonth / 1_000_000
  const lowerCandidate = paygSlope > 0 ? ptuFixed / paygSlope : Number.NaN
  const lower = Number.isFinite(lowerCandidate) && lowerCandidate >= 0 && lowerCandidate <= ptuCapacityRaw
    ? lowerCandidate
    : null

  const slopeDelta = paygSlope - spilloverSlope
  const slopeTolerance = Math.max(
    1e-12,
    1e-9 * Math.max(Math.abs(paygSlope), Math.abs(spilloverSlope)),
  )
  if (Math.abs(slopeDelta) <= slopeTolerance) {
    return { lower, upper: null }
  }

  const upperCandidate = (ptuFixed - spilloverSlope * ptuCapacityRaw) / slopeDelta
  const upper = Number.isFinite(upperCandidate) && upperCandidate > ptuCapacityRaw
    ? upperCandidate
    : null
  return { lower, upper }
}