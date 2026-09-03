---
name: PTU Advisor
description: Operational decision workspace for Azure AI Foundry capacity economics
colors:
  surface-canvas: "#090d14"
  surface-panel: "#111722"
  surface-raised: "#171e2b"
  surface-strong: "#1d2635"
  text-primary: "#edf2f7"
  text-secondary: "#b4bfd0"
  text-muted: "#8592a6"
  border-soft: "#273244"
  border-strong: "#43536c"
  accent-primary: "#6f8cff"
  action-primary: "#7894ff"
  status-success: "#36b795"
  status-warning: "#d69a45"
typography:
  display:
    fontFamily: "Segoe UI Variable Text, Avenir Next, Helvetica Neue, sans-serif"
    fontSize: "clamp(1.55rem, 2vw, 1.9rem)"
    fontWeight: 650
    lineHeight: 1.12
    letterSpacing: "0"
  body:
    fontFamily: "Segoe UI Variable Text, Avenir Next, Helvetica Neue, sans-serif"
    fontSize: "0.91rem"
    fontWeight: 400
    lineHeight: 1.62
    letterSpacing: "0"
  data:
    fontFamily: "SFMono-Regular, Cascadia Code, Roboto Mono, Consolas, monospace"
    fontSize: "0.9rem"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "0"
rounded:
  sm: "6px"
  md: "6px"
  lg: "8px"
  xl: "8px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.action-primary}"
    textColor: "{colors.surface-canvas}"
    rounded: "{rounded.sm}"
    padding: "10px 16px"
  button-secondary:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.sm}"
    padding: "9px 14px"
  field:
    backgroundColor: "{colors.surface-canvas}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.sm}"
    padding: "10px 12px"
  card:
    backgroundColor: "{colors.surface-panel}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.lg}"
    padding: "16px"
---

# Design System: PTU Advisor

## Overview

**Creative North Star: "The Financial Control Room"**

PTU Advisor is an operate-mode analytics workspace built for repeated inspection and comparison. Its near-black canvas, cool layered panels, compact controls, and tabular numeric typography prioritize state, evidence, and economics over decorative expression.

The interface stays restrained so recommendation and warning colors remain meaningful. Broad result canvases give charts, metrics, and cost models room to work, while narrative copy remains limited to a readable measure.

**Direction Contract Provenance:** `FORM: Operate-mode financial control room, preserved incumbent system; seed key: ptu-operational-control-room.` Reproduced with Impeccable 4.1.1 using `--scope direction --mode operate --from ptu-operational-control-room --candidate-count 7`: round 0, assigned position 7 of 7, local approved-pool revision `6c20a02b6dc4`. This records the roll behind the existing direction; it does not establish a new visual direction.

**Key Characteristics:**
- Broad analytical canvas with dense but orderly evidence
- Cool neutral surfaces with one blue interaction accent
- Semantic green, amber, and muted status treatments
- Flat chart surfaces without decorative top stripes
- Monospaced numerals for measured and financial values

## Colors

The palette is a cool dark neutral system with blue reserved for interaction and status colors reserved for decision meaning.

**The Semantic Accent Rule.** Blue communicates interaction; green and amber communicate decision state. Decorative gradients never borrow those meanings.

## Typography

**Display Font:** Segoe UI Variable Text with Avenir Next and Helvetica Neue fallbacks  
**Body Font:** Segoe UI Variable Text with the same workhorse fallback stack  
**Data Font:** SFMono-Regular with Cascadia Code, Roboto Mono, and Consolas fallbacks

**Character:** UI text is compact and neutral. Numeric evidence uses a monospaced stack with tabular figures so values align and remain scannable.

### Hierarchy
- **Display** (650, `clamp(1.55rem, 2vw, 1.9rem)`, 1.12): workspace identity only.
- **Title** (600-650, about `0.96rem-1.16rem`): panels, sections, and chart headers.
- **Body** (400, about `0.8rem-0.91rem`, 1.5-1.62): explanations and supporting copy, capped near 72 characters where practical.
- **Data** (650, responsive `0.9rem-1.15rem`): metrics, costs, percentages, and capacity values.

## Layout

The application shell uses 24px desktop padding and a maximum 1680px canvas. Configuration uses a two-column workspace with a 240-320px context rail. Results use the full canvas; chart grids remain two columns on desktop and collapse to one column below 860px. At 560px and below, controls stack, metric grids use two compact columns, and ECharts use contained labels, 8px side insets, and scrolling legends.

Narrative copy is constrained independently from charts and economics. Cards and fixed-format chart regions use `min-width: 0` to prevent page overflow.

## Elevation & Depth

Depth comes primarily from tonal layering and borders. Resting surfaces use a subtle low shadow; stronger elevation is reserved for sticky navigation, tooltips, menus, and hover feedback.

**The Flat Evidence Rule.** Analytical cards remain visually quiet at rest. Elevation may clarify interaction, but it must not compete with the data.

## Shapes

The system uses compact 6px and 8px radii. Buttons and fields use 6px corners; panels, cards, and tool surfaces use 8px corners. Pills are limited to small status or metadata controls. Borders are 1px; thick side stripes are reserved for genuine warnings and are not used as decoration.

## Components

### Buttons
Primary actions use the light blue action fill with dark text. Secondary actions use raised neutral surfaces and a cool border. All controls retain visible focus rings and a brief pressed state.

### Cards / Containers
Cards use the panel surface, a 1px soft border, and an 8px radius. Chart cards do not use decorative top gradients. Repeated metrics may share borders instead of becoming isolated floating cards.

### Analytical Widgets
Evidence charts use one reusable analytical widget vocabulary: compact title and actions, a truthful headline value with its metric label, concise context or semantic status, an accessible factual summary, then a stable plot region. The desktop Evidence grid remains two columns and collapses to one contained column below 860px.

Cost Explorer is the dominant finance widget. Its selected PTU and commitment context lead into one four-fact comparison strip for PAYG monthly cost, PTU plus spillover monthly cost, monthly difference, and lower/upper break-even. Commitment safety and interpretation stay separate; the same four economics facts are not repeated as cards below the chart.

### Inputs / Fields
Fields use the canvas surface, strong neutral borders, 6px corners, labels above controls, and a visible blue focus ring. Compact selected labels may shorten display text only when the complete value remains available to assistive technology.

### Navigation
The analysis section navigation is compact, horizontally scrollable when needed, and sticky within the result canvas. Active and focus states use the same blue interaction family.

### Status and Provenance
Recommendation colors are semantic. Demo analyses always show a persistent `Synthetic demo data` indicator in the result banner.

## Do's and Don'ts

### Do:
- **Do** use the broad canvas for charts, metrics, and economic comparisons.
- **Do** cap prose near 72 characters and keep numeric values tabular.
- **Do** preserve visible demo provenance and pricing-source context.
- **Do** keep mobile chart labels inside the canvas and move long legends into scrolling controls.

### Don't:
- **Don't** add decorative chart-top gradients, thick informational stripes, or glow effects.
- **Don't** use status colors for decoration.
- **Don't** truncate a selected commitment term without preserving its full accessible value.
- **Don't** collapse desktop chart grids into a narrow reading column.
