import { useCallback, useMemo, useState } from 'react'

type ZoomRange = [number, number] // start%, end% — both 0..100

export type ZoomState = {
  /** Percent range [start%, end%] within the full dataset (0–100). */
  range: ZoomRange
  /** Whether the current view differs from the full analysis window. */
  isDirty: boolean
  /** ISO timestamps at the current zoom window edges, or null if full range. */
  windowStart: string | null
  windowEnd: string | null
}

export function useChartZoom(fullTimestamps: string[]) {
  const [range, setRange] = useState<ZoomRange>([0, 100])

  const isDirty = range[0] > 0.5 || range[1] < 99.5

  const windowEdges = useMemo(() => {
    if (!isDirty || fullTimestamps.length === 0) return { start: null, end: null }
    const startIdx = Math.floor((range[0] / 100) * (fullTimestamps.length - 1))
    const endIdx = Math.ceil((range[1] / 100) * (fullTimestamps.length - 1))
    return {
      start: fullTimestamps[Math.max(0, startIdx)] ?? null,
      end: fullTimestamps[Math.min(fullTimestamps.length - 1, endIdx)] ?? null,
    }
  }, [range, isDirty, fullTimestamps])

  const zoomState: ZoomState = {
    range,
    isDirty,
    windowStart: windowEdges.start,
    windowEnd: windowEdges.end,
  }

  const onDataZoom = useCallback((params: { start?: number; end?: number; batch?: Array<{ start?: number; end?: number }> }) => {
    // ECharts fires datazoom in different shapes depending on the component
    if (params.batch && params.batch.length > 0) {
      const first = params.batch[0]
      if (first.start != null && first.end != null) {
        setRange([first.start, first.end])
      }
    } else if (params.start != null && params.end != null) {
      setRange([params.start, params.end])
    }
  }, [])

  const resetZoom = useCallback(() => {
    setRange([0, 100])
  }, [])

  const getReAnalyzeWindow = useCallback(() => {
    if (!isDirty || !windowEdges.start || !windowEdges.end) return null
    return { window_start: windowEdges.start, window_end: windowEdges.end }
  }, [isDirty, windowEdges])

  return { zoomState, onDataZoom, resetZoom, getReAnalyzeWindow, setRange }
}
