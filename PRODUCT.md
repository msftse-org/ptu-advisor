# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

PTU Advisor primarily serves Solution Engineers and Cloud Solution Architects who need a fast, defensible recommendation for an Azure AI Foundry deployment. Enterprise customers and product or operations teams use the same evidence to understand capacity and commitment tradeoffs.

## Product Purpose

PTU Advisor compares Provisioned Throughput Units (PTU) with Pay-As-You-Go (PAYG) for Azure AI Foundry deployments. It combines historical usage signals, four-dimension readiness scoring, break-even analysis, and hybrid PTU plus PAYG spillover modeling into an explainable recommendation with cost context.

## Positioning

The product turns observable deployment telemetry and explicit pricing assumptions into a repeatable PTU decision. It keeps the recommendation, evidence, economic model, and adjustable assumptions in one workflow rather than relying on manual monitoring review and subjective judgment.

## Operating Context

Users can analyze a discovered Azure deployment, run a clearly labeled synthetic demo, or use the manual PTU calculator without an Azure connection. The React dashboard supports interactive evidence review and what-if analysis; the same analysis domain is also available through the FastAPI API and Typer CLI.

## Capabilities and Constraints

- Produces `PTU Recommended`, `Borderline`, `PTU Not Recommended`, or insufficient-data outcomes.
- Evaluates Workload Shape, Capacity Pressure, Latency Sensitivity, and Load Predictability.
- Compares PAYG, PTU, and hybrid PTU plus spillover economics, including break-even ranges and commitment assumptions.
- Supports live Azure discovery and historical metrics when the user has the required Azure access.
- Supports synthetic demo scenarios; demo results must remain visibly identified as synthetic.
- Exposes report and data export actions implemented by the frontend.
- Uses historical, observable inputs and explicit assumptions. It does not purchase PTU, predict future traffic, or make a contractual capacity commitment.

## Brand Commitments

The product name is PTU Advisor. Product language is factual, concise, and operational. Recommendations must expose confidence, evidence, assumptions, and limitations without marketing claims.

## Evidence on Hand

- Product behavior and setup: `README.md`
- Implemented product requirements and non-goals: `docs/PRD.md`
- Current architecture and delivery surfaces: `CODEBASE_OVERVIEW.md`
- Frontend behavior and tests: `frontend/src/`

No customer testimonials, adoption claims, or independent outcome benchmarks are present in the repository and must not be fabricated.

## Product Principles

- Ground recommendations in observable data and named assumptions.
- Make cost math and recommendation rationale inspectable.
- Distinguish synthetic demonstrations from production telemetry at all times.
- Preserve comparison context so users can evaluate commitment risk, not just a headline verdict.
- Treat estimates as decision support, not contractual guidance.
