import '@testing-library/jest-dom/vitest'

// Mock HTMLCanvasElement.getContext so ECharts / zrender don't crash in JSDOM
// (JSDOM doesn't ship a canvas implementation).
const noop = () => {}
const mockGetContext = function (_this: HTMLCanvasElement, contextId: string) {
  if (contextId === '2d') {
    return {
      canvas: _this,
      clearRect: noop,
      fillRect: noop,
      strokeRect: noop,
      fillText: noop,
      strokeText: noop,
      measureText: (text: string) => ({ width: text.length * 8 }),
      beginPath: noop,
      closePath: noop,
      moveTo: noop,
      lineTo: noop,
      arc: noop,
      arcTo: noop,
      rect: noop,
      fill: noop,
      stroke: noop,
      clip: noop,
      save: noop,
      restore: noop,
      scale: noop,
      rotate: noop,
      translate: noop,
      transform: noop,
      setTransform: noop,
      resetTransform: noop,
      createLinearGradient: () => ({ addColorStop: noop }),
      createRadialGradient: () => ({ addColorStop: noop }),
      createPattern: () => null,
      drawImage: noop,
      getImageData: () => ({ data: new Uint8ClampedArray(0), width: 0, height: 0 }),
      putImageData: noop,
      createImageData: () => ({ data: new Uint8ClampedArray(0), width: 0, height: 0 }),
      setLineDash: noop,
      getLineDash: () => [] as number[],
      bezierCurveTo: noop,
      quadraticCurveTo: noop,
      isPointInPath: () => false,
      isPointInStroke: () => false,
      ellipse: noop,
      globalAlpha: 1,
      globalCompositeOperation: 'source-over',
      fillStyle: '#000',
      strokeStyle: '#000',
      lineWidth: 1,
      lineCap: 'butt',
      lineJoin: 'miter',
      miterLimit: 10,
      lineDashOffset: 0,
      shadowBlur: 0,
      shadowColor: 'rgba(0,0,0,0)',
      shadowOffsetX: 0,
      shadowOffsetY: 0,
      font: '10px sans-serif',
      textAlign: 'start',
      textBaseline: 'alphabetic',
      direction: 'ltr',
      imageSmoothingEnabled: true,
    } as unknown as CanvasRenderingContext2D
  }
  return null
}
HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, contextId: string) {
  return mockGetContext(this, contextId)
} as unknown as typeof HTMLCanvasElement.prototype.getContext
