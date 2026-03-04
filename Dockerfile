# ============================================================
# PTU Advisor - Dockerfile
# ============================================================
# Multi-stage build: Node.js (frontend) + Python (backend)
# Serves the React SPA via FastAPI on a single port.
#
# Usage:
#   docker build -t ptu-advisor .
#   docker run -p 8000:8000 ptu-advisor                        # app
#   docker run ptu-advisor ptu-advisor demo --scenario ptu-recommended  # CLI
# ============================================================

# --------------- stage 1: build frontend --------------------
FROM node:20-slim AS frontend

WORKDIR /frontend

# Install dependencies first (layer caching)
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

# Copy source and build
COPY frontend/ ./
RUN npm run build

# --------------- stage 2: build Python wheel ----------------
FROM python:3.11-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir hatchling

COPY pyproject.toml README.md ./
COPY ptu_advisor/ ptu_advisor/

RUN pip wheel --no-deps --wheel-dir /build/wheels .

# --------------- stage 3: runtime ---------------------------
FROM python:3.11-slim AS runtime

LABEL maintainer="Microsoft <ptu-advisor@microsoft.com>"
LABEL description="PTU Advisor – Azure AI Foundry PTU vs PAYG recommendation tool"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AZURE_CORE_ONLY_SHOW_ERRORS=1

# Install Azure CLI so AzureCliCredential can work inside container
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg && \
    curl -sL https://aka.ms/InstallAzureCLIDeb | bash && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 advisor && \
    useradd --uid 1000 --gid advisor --create-home advisor

WORKDIR /app

# Install the wheel + openai SDK (for LLM explanations)
COPY --from=builder /build/wheels/*.whl /tmp/wheels/
RUN pip install --no-cache-dir /tmp/wheels/*.whl \
        openai>=1.12.0 && \
    rm -rf /tmp/wheels

# Copy built frontend into /app/static
COPY --from=frontend /frontend/dist /app/static

# Copy report templates and create outputs directory
COPY ptu_advisor/report/templates/ /app/ptu_advisor/report/templates/
RUN mkdir -p /app/outputs && chown advisor:advisor /app/outputs

USER advisor

# Single port for both API and frontend
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Launch FastAPI (serves API + static frontend)
CMD ["uvicorn", "ptu_advisor.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
