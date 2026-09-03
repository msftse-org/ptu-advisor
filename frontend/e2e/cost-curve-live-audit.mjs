import fs from 'node:fs/promises'
import path from 'node:path'
import { chromium } from '@playwright/test'

const outputDir = path.resolve('test-results')
const desktopPath = path.join(outputDir, 'cost-curve-35ptu-desktop.png')
const mobilePath = path.join(outputDir, 'cost-curve-35ptu-mobile.png')
const reportPath = path.join(outputDir, 'cost-curve-35ptu-visual-report.json')

await fs.mkdir(outputDir, { recursive: true })

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

function waitForAnalysis() {
  return page.waitForResponse(
    (response) => response.url().includes('/api/analyze') && response.status() === 200,
    { timeout: 60_000 },
  )
}

async function waitForStableAnalysis() {
  await page.waitForFunction(() => {
    const status = document.querySelector('.assumption-status')
    return status?.textContent?.includes('Changes apply automatically') ?? false
  })
  await page.waitForTimeout(350)
}

async function positionCostExplorer() {
  await page.evaluate(() => {
    const chart = document.querySelector('.cost-explorer-widget')
    const nav = document.querySelector('.analysis-section-nav')
    if (!(chart instanceof HTMLElement) || !(nav instanceof HTMLElement)) {
      throw new Error('Cost Explorer or analysis navigation was not found')
    }

    window.scrollTo({
      top: chart.getBoundingClientRect().top + window.scrollY - nav.getBoundingClientRect().height - 16,
      behavior: 'instant',
    })
  })
  await page.waitForTimeout(250)
}

async function inspectChart() {
  return page.evaluate(async () => {
    const wrapper = document.querySelector('.cost-explorer-widget .echarts-for-react')
    if (!(wrapper instanceof HTMLElement)) throw new Error('Cost Explorer ECharts wrapper was not found')

    const { echarts } = await import('/src/charts/echarts-setup.ts')
    const chart = echarts.getInstanceByDom(wrapper)
    if (!chart) throw new Error('Cost Explorer ECharts instance was not found')

    chart.resize()
    const model = chart.getModel()
    const option = chart.getOption()
    const publicSeries = option.series.filter((series) => !series.name.startsWith('_'))
    const customSeries = option.series.find((series) => series.name === '_savings_fill')
    const customModel = model.getSeriesByName('_savings_fill')[0]
    const legendModel = model.getComponent('legend')
    const paygData = option.series.find((series) => series.name === 'PAYG').data
    const hybridData = option.series.find((series) => series.name === 'PTU + Spillover').data
    const markLines = option.series.find((series) => series.name === 'PAYG').markLine.data
    const capacityMarker = markLines.find((marker) => marker.label?.formatter?.includes('PTU capacity'))
    const capacity = capacityMarker?.xAxis ?? 0
    const flatValues = hybridData
      .filter(([x]) => x <= capacity)
      .map(([, value]) => value)
    const differences = paygData.map(([x, payg], index) => ({
      x,
      value: payg - hybridData[index][1],
    }))
    const crossingSegments = []
    for (let index = 0; index < differences.length - 1; index += 1) {
      const start = differences[index]
      const end = differences[index + 1]
      if ((start.value < 0 && end.value > 0) || (start.value > 0 && end.value < 0)) {
        crossingSegments.push([start.x, end.x])
      }
    }

    const canvas = wrapper.querySelector('canvas')
    const context = canvas.getContext('2d')
    const image = context.getImageData(0, 0, canvas.width, canvas.height).data
    let blueLinePixels = 0
    let greenLinePixels = 0
    let translucentGreenPixels = 0
    for (let index = 0; index < image.length; index += 4) {
      const red = image[index]
      const green = image[index + 1]
      const blue = image[index + 2]
      const alpha = image[index + 3]
      if (Math.abs(red) < 18 && Math.abs(green - 120) < 18 && Math.abs(blue - 212) < 18 && alpha > 180) {
        blueLinePixels += 1
      }
      if (Math.abs(red) < 18 && Math.abs(green - 212) < 18 && Math.abs(blue - 170) < 18 && alpha > 180) {
        greenLinePixels += 1
      }
      if (green > red + 40 && green > blue && alpha >= 20 && alpha <= 90) {
        translucentGreenPixels += 1
      }
    }

    const publicZ = publicSeries.map((series) => ({
      name: series.name,
      z: model.getSeriesByName(series.name)[0].get('z'),
    }))
    const savingsZ = customModel.get('z')
    const savingsData = customSeries.data

    return {
      chartSize: { width: chart.getWidth(), height: chart.getHeight() },
      xExtent: model.getComponent('xAxis').axis.scale.getExtent(),
      yExtent: model.getComponent('yAxis').axis.scale.getExtent(),
      xTicks: model.getComponent('xAxis').axis.scale.getTicks().map((tick) => tick.value),
      yTicks: model.getComponent('yAxis').axis.scale.getTicks().map((tick) => tick.value),
      legendNames: legendModel.getData().map((item) => item.get('name')),
      customEncode: customSeries.encode,
      seriesZ: [...publicZ, { name: customSeries.name, z: savingsZ }],
      savingsBehindLines: publicZ.every((series) => savingsZ < series.z),
      savingsSegments: savingsData.length,
      savingsRange: [savingsData[0][0], savingsData.at(-1)[1]],
      flatPtuPhase: {
        capacity,
        pointCount: flatValues.length,
        minCost: Math.min(...flatValues),
        maxCost: Math.max(...flatValues),
        costSpan: Math.max(...flatValues) - Math.min(...flatValues),
      },
      crossingSegments,
      markerPixels: Object.fromEntries(markLines.map((marker) => [marker.label?.formatter ?? '', chart.convertToPixel({ xAxisIndex: 0 }, marker.xAxis)])),
      pixels: {
        canvasWidth: canvas.width,
        canvasHeight: canvas.height,
        blueLinePixels,
        greenLinePixels,
        translucentGreenPixels,
      },
    }
  })
}

async function inspectLayout() {
  const region = page.getByRole('region', { name: 'Cost Explorer analytical widget' })
  const frame = region.locator('.cost-explorer-chart-frame')
  const canvas = frame.locator('canvas').first()
  const regionBox = await region.boundingBox()
  const frameBox = await frame.boundingBox()
  const canvasBox = await canvas.boundingBox()

  return {
    viewport: await page.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight })),
    regionBox,
    frameBox,
    canvasBox,
    regionOverflow: await region.evaluate((element) => ({
      horizontal: element.scrollWidth > element.clientWidth,
      vertical: element.scrollHeight > element.clientHeight,
    })),
    pageHorizontalOverflow: await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth),
    canvasContained: frameBox != null && canvasBox != null &&
      canvasBox.x >= frameBox.x - 0.5 && canvasBox.x + canvasBox.width <= frameBox.x + frameBox.width + 0.5 &&
      canvasBox.y >= frameBox.y - 0.5 && canvasBox.y + canvasBox.height <= frameBox.y + frameBox.height + 0.5,
    chartAriaLabel: await frame.getAttribute('aria-label'),
  }
}

function pngDimensions(buffer) {
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
    bytes: buffer.length,
  }
}

await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' })
await page.getByRole('button', { name: 'Demo Mode' }).click()
await Promise.all([
  waitForAnalysis(),
  page.getByRole('button', { name: 'Run Analysis' }).click(),
])
await page.getByRole('region', { name: 'Cost Explorer analytical widget' }).waitFor({ state: 'visible', timeout: 60_000 })

const regionSelect = page.getByRole('combobox', { name: 'Azure Region' })
if (await regionSelect.inputValue() !== 'swedencentral') {
  const response = waitForAnalysis()
  await regionSelect.selectOption('swedencentral')
  await response
  await waitForStableAnalysis()
}

const termSelect = page.getByRole('combobox', { name: /PTU Pricing Term/ })
if (await termSelect.inputValue() !== 'Monthly Commitment (Estimated 64% off)') {
  const response = waitForAnalysis()
  await termSelect.selectOption('Monthly Commitment (Estimated 64% off)')
  await response
  await waitForStableAnalysis()
}

const slider = page.getByRole('slider', { name: /PTU Baseline Coverage/ })
if (await slider.inputValue() !== '35') {
  const response = waitForAnalysis()
  await slider.evaluate((element) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
    setter.call(element, '35')
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await response
  await waitForStableAnalysis()
}

await page.getByRole('heading', { name: /Cost Explorer.*35 PTU/ }).waitFor({ state: 'visible', timeout: 60_000 })
await waitForStableAnalysis()

await positionCostExplorer()
const desktopChart = await inspectChart()
const desktopLayout = await inspectLayout()
const desktopBuffer = await page.getByRole('region', { name: 'Cost Explorer analytical widget' }).screenshot({
  path: desktopPath,
  animations: 'disabled',
  scale: 'css',
})

await page.setViewportSize({ width: 390, height: 844 })
await page.waitForTimeout(400)
await positionCostExplorer()
const mobileChart = await inspectChart()
const mobileLayout = await inspectLayout()
const mobileBuffer = await page.getByRole('region', { name: 'Cost Explorer analytical widget' }).screenshot({
  path: mobilePath,
  animations: 'disabled',
  scale: 'css',
})

const report = {
  status: 'PASS',
  scenario: {
    baselinePtu: Number(await slider.inputValue()),
    region: await regionSelect.inputValue(),
    reservationType: await termSelect.inputValue(),
    breakEvenText: await page.locator('.cost-comparison-fact').filter({ hasText: 'Break-even range' }).innerText(),
  },
  desktop: {
    chart: desktopChart,
    layout: desktopLayout,
    screenshot: { file: path.relative(process.cwd(), desktopPath), ...pngDimensions(desktopBuffer) },
  },
  mobile: {
    chart: mobileChart,
    layout: mobileLayout,
    screenshot: { file: path.relative(process.cwd(), mobilePath), ...pngDimensions(mobileBuffer) },
  },
  diagnostics,
}

report.checks = {
  desktopYMaxIsSane: desktopChart.yExtent[1] <= 50_000,
  mobileYMaxIsSane: mobileChart.yExtent[1] <= 50_000,
  exactPublicLegend: JSON.stringify(desktopChart.legendNames) === JSON.stringify(['PAYG', 'PTU + Spillover']) &&
    JSON.stringify(mobileChart.legendNames) === JSON.stringify(['PAYG', 'PTU + Spillover']),
  internalSeriesExcluded: !desktopChart.legendNames.includes('_savings_fill') && !mobileChart.legendNames.includes('_savings_fill'),
  explicitAxisEncoding: JSON.stringify(desktopChart.customEncode) === JSON.stringify({ x: [0, 1], y: [2, 3, 4, 5] }),
  flatPtuPhaseVisible: desktopChart.flatPtuPhase.pointCount > 1 && desktopChart.flatPtuPhase.costSpan === 0,
  twoCrossingsVisible: desktopChart.crossingSegments.length === 2,
  savingsBehindLines: desktopChart.savingsBehindLines && mobileChart.savingsBehindLines,
  savingsBandRendered: desktopChart.pixels.translucentGreenPixels > 0 && mobileChart.pixels.translucentGreenPixels > 0,
  bothLinesRendered: desktopChart.pixels.blueLinePixels > 0 && desktopChart.pixels.greenLinePixels > 0 &&
    mobileChart.pixels.blueLinePixels > 0 && mobileChart.pixels.greenLinePixels > 0,
  noOverflow: !desktopLayout.regionOverflow.horizontal && !desktopLayout.pageHorizontalOverflow && desktopLayout.canvasContained &&
    !mobileLayout.regionOverflow.horizontal && !mobileLayout.pageHorizontalOverflow && mobileLayout.canvasContained,
  zeroBrowserErrors: Object.values(diagnostics).every((items) => items.length === 0),
}
report.status = Object.values(report.checks).every(Boolean) ? 'PASS' : 'FAIL'

await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`)
console.log(JSON.stringify(report, null, 2))

await browser.close()
if (report.status !== 'PASS') process.exitCode = 1