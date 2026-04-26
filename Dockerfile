# Multi-stage build for smaller image size
FROM python:3.11-slim as base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
COPY requirements.txt .

# Upgrade pip first (older pip has issues with truncated JSON index responses)
RUN pip install --no-cache-dir --upgrade pip

# Install Python dependencies (with retries for unstable network)
# --prefer-binary: avoid source builds; --retries 10: tolerate flaky network
RUN pip install --no-cache-dir --prefer-binary --retries 10 --timeout 120 -r requirements.txt

# Development stage (with code mounted as volume)
FROM base as development

# Code will be mounted as volume in docker-compose.dev.yml
# No need to copy code here

EXPOSE 8000

CMD ["uvicorn", "bot.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production stage (with code baked in)
FROM base as production

# Copy application code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "bot.main:app", "--host", "0.0.0.0", "--port", "8000"]
