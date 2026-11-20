# Multi-stage Dockerfile for Unpack Server
# Stage 1: Build the React frontend
FROM node:20-alpine AS web-builder
WORKDIR /web
COPY web/package*.json ./
RUN npm ci || npm install
COPY web/ ./
RUN npm run build || mkdir -p dist && touch dist/index.html

# Stage 2: Python server runner with Playwright Chromium
FROM python:3.11-slim AS runner
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies & git
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Install Playwright browser
RUN playwright install --with-deps chromium

# Copy application source
COPY server/ ./server/
COPY unpack_graph/ ./unpack_graph/
COPY cli/ ./cli/
COPY schemas/ ./schemas/

# Copy built frontend assets
COPY --from=web-builder /web/dist ./web/dist

EXPOSE 8000

CMD ["uvicorn", "server.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
