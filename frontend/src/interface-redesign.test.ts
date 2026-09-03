import { describe, expect, it } from 'vitest'
import indexHtml from '../index.html?raw'
import interfaceCss from './interface-redesign.css?raw'
import legacyCss from './styles.css?raw'
import { PTU_CHART_THEME } from './charts/theme'

describe('dark interface theme', () => {
  it('declares dark browser chrome and dark operational surfaces', () => {
    expect(interfaceCss).toContain('color-scheme: dark')
    expect(interfaceCss).toContain('--surface-0: #090d14')
    expect(interfaceCss).toContain('--surface-1: #111722')
    expect(interfaceCss).toContain('--text-primary: #edf2f7')
  })

  it('uses readable dark chart tokens', () => {
    expect(PTU_CHART_THEME.title.textStyle.color).toBe('#edf2f7')
    expect(PTU_CHART_THEME.dataZoom[0].backgroundColor).toBe('#171e2b')
    expect(PTU_CHART_THEME.tooltip.backgroundColor).toBe('rgba(8, 12, 18, 0.98)')
  })

  it('uses restrained product typography and flat form sections', () => {
    expect(interfaceCss).toContain('--font-data: "SFMono-Regular"')
    expect(interfaceCss).toContain('font-family: var(--font-ui)')
    expect(interfaceCss).toContain('.advisor-form-grid fieldset')
    expect(interfaceCss).toContain('background: transparent')
  })

  it('uses local dark browser branding', () => {
    expect(indexHtml).toContain('name="theme-color" content="#090d14"')
    expect(indexHtml).toContain('href="/favicon.svg"')
    expect(indexHtml).not.toContain('cdn-icons-png.flaticon.com')
  })

  it('uses elevated, directional DOM tooltips', () => {
    expect(interfaceCss).toContain('.tip-bubble::before')
    expect(interfaceCss).toContain('.info-tip[data-tooltip-align="center"]')
    expect(interfaceCss).toContain('backdrop-filter: blur(18px)')
    expect(interfaceCss).toContain('cubic-bezier(0.2, 0, 0, 1)')
    expect(interfaceCss).toContain('text-wrap: pretty')
  })

  it('uses a structured chart tooltip surface', () => {
    expect(PTU_CHART_THEME.tooltip.borderColor).toBe('#3b4a63')
    expect(PTU_CHART_THEME.tooltip.textStyle.fontFamily).toContain('Segoe UI')
    expect(PTU_CHART_THEME.tooltip.extraCssText).toContain('padding: 10px 12px')
    expect(PTU_CHART_THEME.tooltip.extraCssText).toContain('backdrop-filter: blur(18px)')
  })

  it('keeps calculator detail component styles in one design layer', () => {
    expect(legacyCss).not.toContain('.calc-details-row')
    expect(legacyCss).not.toMatch(/\.calc-detail-(card|label|value|sub)/)
    expect(interfaceCss.match(/^\.calc-details-row\s*\{/gm)).toHaveLength(1)
    for (const selector of ['card', 'label', 'value', 'sub']) {
      expect(interfaceCss.match(new RegExp(`^\\.calc-detail-${selector}\\s*\\{`, 'gm'))).toHaveLength(1)
    }
  })

  it('lets deployment scope use the full result grid width', () => {
    expect(interfaceCss).toMatch(/\.results-v2 \.glance-card-scope\s*\{[^}]*grid-column:\s*1\s*\/\s*-1/s)
  })

  it('gives results a broad desktop canvas without changing the two-column chart grid', () => {
    expect(interfaceCss).toMatch(/\.container\s*\{[^}]*max-width:\s*1680px/s)
    expect(interfaceCss).toMatch(/\.results-container\s*\{[^}]*max-width:\s*1680px/s)
    expect(interfaceCss).toMatch(/\.chart-grid,\s*\.chart-grid-v2\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/s)
  })

  it('gives prompt cache evidence two full-width desktop columns and stacks them on mobile', () => {
    expect(interfaceCss).toMatch(/\.prompt-cache-composition\s*\{[^}]*grid-column:\s*1\s*\/\s*-1[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/s)
    expect(interfaceCss).toMatch(/@media\s*\(max-width:\s*860px\)[\s\S]*?\.prompt-cache-composition\s*\{[^}]*grid-template-columns:\s*1fr/s)
  })

  it('removes non-semantic cache stripes and decorative chart-top gradients', () => {
    const cacheRule = legacyCss.match(/\.cache-impact-strip\s*\{([^}]*)\}/s)?.[1] ?? ''
    expect(cacheRule).not.toContain('border-left')
    expect(cacheRule).not.toContain('linear-gradient')
    expect(legacyCss).not.toContain('.results-v2 .chart-grid-v2 .chart-card::before')
    expect(interfaceCss).not.toContain('.chart-card::before')
  })
})