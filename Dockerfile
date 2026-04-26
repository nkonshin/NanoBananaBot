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

# Install Python dependencies (with retries for unstable network)
RUN pip install --no-cache-dir --retries 10 --timeout 60 -r requirements.txt

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
