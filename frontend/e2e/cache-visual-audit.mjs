import path from 'node:path'
import { chromium } from '@playwright/test'

const reviewDir = path.resolve('..', '.impeccable', 'review')
const cacheCompositionSelector = '.prompt-cache-composition'
const stickyNavSelector = '.analysis-section-nav'
const stickyNavGap = 12
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({
  viewport: { width: 1440, height: 1000 },
  deviceScaleFactor: 1,
})

const diagnostics = {
  consoleErrors: [],
  pageErrors: [],
  requestFailures: [],
  httpErrors: [],
}

page.on('console', (message) => {
  if (message.type() === 'error') diagnostics.consoleErrors.push(message.text())
})
page.on('pageerror', (error) => diagnostics.pageErrors.push(error.message))
page.on('requestfailed', (request) => {
  diagnostics.requestFailures.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText ?? 'unknown'}`)
})
page.on('response', (response) => {
  if (response.status() >= 400) diagnostics.httpErrors.push(`${response.status()} ${response.url()}`)
})

async function waitForCharts() {
  await page.waitForFunction(() => document.querySelectorAll('.prompt-cache-composition canvas').length === 2)
  await waitForVisualSettling(cacheCompositionSelector)
}

async function waitForVisualSettling(trackedSelector) {
  await page.waitForFunction(() => document.getAnimations().every((animation) => {
    const iterations = animation.effect?.getComputedTiming().iterations
    return animation.playState !== 'running' || iterations === Infinity
  }))
  await page.evaluate((selector) => new Promise((resolve) => {
    const tracked = document.querySelector(selector)
    let previous = null
    let stableFrames = 0

    const checkFrame = () => {
      const rect = tracked?.getBoundingClientRect()
      const current = [
        window.scrollX,
        window.scrollY,
        rect?.x ?? 0,
        rect?.y ?? 0,
        rect?.width ?? 0,
        rect?.height ?? 0,
      ]
      const isStable = previous?.every((value, index) => Math.abs(value - current[index]) < 0.1) ?? false
      stableFrames = isStable ? stableFrames + 1 : 0
      previous = current

      if (stableFrames >= 4) resolve()
      else requestAnimationFrame(checkFrame)
    }

    requestAnimationFrame(checkFrame)
  }), trackedSelector)
}

async function waitForExpandedUiToClose() {
  await page.locator('.chart-modal-backdrop').waitFor({ state: 'detached' })
  await page.waitForFunction(() => document.querySelectorAll('.is-chart-expanded').length === 0)
  await waitForVisualSettling(cacheCompositionSelector)
}

async function positionCacheCompositionBelowStickyNav() {
  const group = page.getByRole('group', { name: 'Prompt cache evidence' })
  await waitForExpandedUiToClose()
  await group.evaluate((element) => element.scrollIntoView({ block: 'start', behavior: 'instant' }))
  await waitForVisualSettling(cacheCompositionSelector)

  for (let attempt = 0; attempt < 3; attempt += 1) {
    const delta = await page.evaluate(({ groupSelector, navSelector, gap }) => {
      const composition = document.querySelector(groupSelector)
      const nav = document.querySelector(navSelector)
      if (!(composition instanceof HTMLElement) || !(nav instanceof HTMLElement)) {
        throw new Error('Prompt cache composition or analysis section nav was not found')
      }

      const compositionTop = composition.getBoundingClientRect().top
      const desiredTop = nav.getBoundingClientRect().bottom + gap
      const adjustment = compositionTop - desiredTop
      window.scrollBy({ top: adjustment, behavior: 'instant' })
      return adjustment
    }, {
      groupSelector: cacheCompositionSelector,
      navSelector: stickyNavSelector,
      gap: stickyNavGap,
    })
    await waitForVisualSettling(cacheCompositionSelector)
    if (Math.abs(delta) < 0.5) break
  }
}

function pngDimensions(buffer) {
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  }
}

async function captureCanonicalScreenshot(fileName) {
  const buffer = await page.screenshot({ path: path.join(reviewDir, fileName), scale: 'css' })
  return {
    file: `.impeccable/review/${fileName}`,
    capture: 'viewport',
    ...pngDimensions(buffer),
    bytes: buffer.length,
  }
}

async function measureCacheComposition() {
  const group = page.getByRole('group', { name: 'Prompt cache evidence' })

  const groupStyle = await group.evaluate((element) => {
    const style = getComputedStyle(element)
    return {
      gridColumnStart: style.gridColumnStart,
      gridColumnEnd: style.gridColumnEnd,
      gridTemplateColumns: style.gridTemplateColumns,
    }
  })
  const cards = await group.locator(':scope > [role="region"]').evaluateAll((nodes) => nodes.map((node) => {
    const rect = node.getBoundingClientRect()
    const canvas = node.querySelector('canvas')?.getBoundingClientRect()
    const heading = node.querySelector('.widget-header')?.getBoundingClientRect()
    const visibleTop = Math.max(rect.top, 0)
    const visibleBottom = Math.min(rect.bottom, window.innerHeight)
    return {
      name: node.getAttribute('aria-label'),
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height,
      right: rect.right,
      bottom: rect.bottom,
      visibleHeight: Math.max(0, visibleBottom - visibleTop),
      contentOverflow: node.scrollWidth > node.clientWidth || node.scrollHeight > node.clientHeight,
      canvasContained: canvas == null || (
        canvas.left >= rect.left && canvas.right <= rect.right &&
        canvas.top >= rect.top && canvas.bottom <= rect.bottom
      ),
      heading: heading == null ? null : {
        x: heading.x,
        y: heading.y,
        width: heading.width,
        height: heading.height,
        bottom: heading.bottom,
        visible: heading.bottom > 0 && heading.top < window.innerHeight,
      },
      canvas: canvas == null ? null : {
        x: canvas.x,
        y: canvas.y,
        width: canvas.width,
        height: canvas.height,
        bottom: canvas.bottom,
        visibleHeight: Math.max(0, Math.min(canvas.bottom, window.innerHeight) - Math.max(canvas.top, 0)),
      },
    }
  }))
  const viewport = await page.evaluate(({ groupSelector, navSelector }) => {
    const composition = document.querySelector(groupSelector)?.getBoundingClientRect()
    const nav = document.querySelector(navSelector)?.getBoundingClientRect()
    return {
      innerWidth,
      innerHeight,
      scrollX,
      scrollY,
      documentWidth: document.documentElement.scrollWidth,
      documentHeight: document.documentElement.scrollHeight,
      horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      composition: composition == null ? null : {
        x: composition.x,
        y: composition.y,
        width: composition.width,
        height: composition.height,
        right: composition.right,
        bottom: composition.bottom,
      },
      stickyNav: nav == null ? null : {
        x: nav.x,
        y: nav.y,
        width: nav.width,
        height: nav.height,
        right: nav.right,
        bottom: nav.bottom,
      },
    }
  }, { groupSelector: cacheCompositionSelector, navSelector: stickyNavSelector })
  const roles = {
    volumeRegion: await page.getByRole('region', { name: 'Prompt Cache Volume analytical widget' }).count(),
    efficiencyRegion: await page.getByRole('region', { name: 'Cache Efficiency analytical widget' }).count(),
    volumeChart: await page.getByRole('img', { name: 'Active and cached prompt token volume over time' }).count(),
    efficiencyChart: await page.getByRole('img', { name: 'Prompt cache match percentage over time' }).count(),
  }

  return { groupStyle, cards, viewport, roles }
}

await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' })
await page.getByRole('button', { name: 'Demo Mode' }).click()
await page.getByRole('button', { name: 'Run Analysis' }).click()
await page.getByRole('group', { name: 'Prompt cache evidence' }).waitFor({ state: 'visible', timeout: 30_000 })
await waitForCharts()

await positionCacheCompositionBelowStickyNav()
const desktop = await measureCacheComposition()
const desktopScreenshot = await captureCanonicalScreenshot('desktop.png')

const volumeCard = page.getByRole('region', { name: 'Prompt Cache Volume analytical widget' })
const efficiencyCard = page.getByRole('region', { name: 'Cache Efficiency analytical widget' })
await page.getByRole('button', { name: 'Expand Prompt Cache Volume' }).click()
await volumeCard.waitFor({ state: 'visible' })
const volumeExpansion = {
  volumeExpanded: await volumeCard.evaluate((node) => node.classList.contains('is-chart-expanded')),
  efficiencyExpanded: await efficiencyCard.evaluate((node) => node.classList.contains('is-chart-expanded')),
  position: await volumeCard.evaluate((node) => getComputedStyle(node).position),
}
await page.getByRole('button', { name: 'Collapse Prompt Cache Volume' }).click()
await waitForExpandedUiToClose()
await page.getByRole('button', { name: 'Expand Cache Efficiency' }).click()
const efficiencyExpansion = {
  volumeExpanded: await volumeCard.evaluate((node) => node.classList.contains('is-chart-expanded')),
  efficiencyExpanded: await efficiencyCard.evaluate((node) => node.classList.contains('is-chart-expanded')),
  position: await efficiencyCard.evaluate((node) => getComputedStyle(node).position),
}
await page.keyboard.press('Escape')
await waitForExpandedUiToClose()

await page.setViewportSize({ width: 390, height: 844 })
await waitForCharts()
await positionCacheCompositionBelowStickyNav()
const mobile = await measureCacheComposition()
const mobileScreenshot = await captureCanonicalScreenshot('mobile.png')

const desktopColumns = desktop.cards.length === 2 &&
  Math.abs(desktop.cards[0].y - desktop.cards[1].y) < 2 &&
  Math.abs(desktop.cards[0].width - desktop.cards[1].width) < 2
const mobileStack = mobile.cards.length === 2 &&
  Math.abs(mobile.cards[0].x - mobile.cards[1].x) < 2 &&
  mobile.cards[1].y >= mobile.cards[0].bottom
const mobileFirstCardPositioned = mobile.cards.length === 2 && mobile.viewport.stickyNav != null &&
  mobile.cards[0].y >= mobile.viewport.stickyNav.bottom + stickyNavGap - 0.5 &&
  mobile.cards[0].y < mobile.viewport.innerHeight
const mobileFirstWidgetVisible = mobile.cards[0]?.bottom <= mobile.viewport.innerHeight &&
  mobile.cards[0]?.heading?.visible === true &&
  (mobile.cards[0]?.canvas?.visibleHeight ?? 0) >= 120
const mobileSecondWidgetVisible = mobile.cards[1]?.y < mobile.viewport.innerHeight &&
  mobile.cards[1]?.visibleHeight >= 160 &&
  mobile.cards[1]?.heading?.visible === true

const checks = {
  desktopViewport: desktop.viewport.innerWidth === 1440 && desktop.viewport.innerHeight === 1000,
  desktopTwoEqualColumns: desktopColumns,
  desktopSpansEvidenceGrid: desktop.groupStyle.gridColumnStart === '1' && desktop.groupStyle.gridColumnEnd === '-1',
  desktopBothWidgetsVisible: desktop.cards.every((card) => card.y >= 0 && card.bottom <= desktop.viewport.innerHeight),
  desktopContained: desktop.cards.every((card) => !card.contentOverflow && card.canvasContained),
  desktopNoPageOverflow: !desktop.viewport.horizontalOverflow,
  desktopScreenshotDimensions: desktopScreenshot.width === 1440 && desktopScreenshot.height === 1000,
  mobileViewport: mobile.viewport.innerWidth === 390 && mobile.viewport.innerHeight === 844,
  mobileStacked: mobileStack,
  mobileFirstCardBelowStickyNav: mobileFirstCardPositioned,
  mobileFirstWidgetAndChartVisible: mobileFirstWidgetVisible,
  mobileSecondWidgetVisible: mobileSecondWidgetVisible,
  mobileContained: mobile.cards.every((card) => !card.contentOverflow && card.canvasContained),
  mobileNoPageOverflow: !mobile.viewport.horizontalOverflow,
  mobileScreenshotDimensions: mobileScreenshot.width === 390 && mobileScreenshot.height === 844,
  accessibleRegionsAndCharts: [...Object.values(desktop.roles), ...Object.values(mobile.roles)].every((count) => count === 1),
  volumeExpandsIndependently: volumeExpansion.volumeExpanded && !volumeExpansion.efficiencyExpanded && volumeExpansion.position === 'fixed',
  efficiencyExpandsIndependently: !efficiencyExpansion.volumeExpanded && efficiencyExpansion.efficiencyExpanded && efficiencyExpansion.position === 'fixed',
  expandedUiFullyRemoved: await page.locator('.chart-modal-backdrop, .is-chart-expanded').count() === 0,
  zeroBrowserErrors: Object.values(diagnostics).every((items) => items.length === 0),
}
const report = {
  status: Object.values(checks).every(Boolean) ? 'PASS' : 'FAIL',
  desktop,
  mobile,
  screenshots: {
    desktop: desktopScreenshot,
    mobile: mobileScreenshot,
  },
  volumeExpansion,
  efficiencyExpansion,
  diagnostics,
  checks,
}

console.log(JSON.stringify(report, null, 2))
await browser.close()
if (report.status === 'FAIL') process.exitCode = 1