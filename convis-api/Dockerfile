# Multi-stage build for FastAPI Backend
FROM python:3.11-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    libespeak-ng1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
# PyTorch CPU-only for Silero VAD (~200MB vs ~2GB with CUDA)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Production stage
FROM base AS production

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    libespeak-ng1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Create necessary directories with proper permissions
RUN mkdir -p uploads/knowledge_base chroma_db logs models/whisper models/piper && \
    chmod -R 755 uploads chroma_db logs models

# Expose port (internal container port)
EXPOSE 8000

# Note: Cloud Run doesn't support HEALTHCHECK directive
# Health checks are configured in Cloud Run service settings instead

# Run the application with gunicorn + uvicorn workers
# Cloud Run sets PORT environment variable, default to 8000 for local development
# Using gunicorn for more reliable startup behavior on Cloud Run
CMD ["sh", "-c", "gunicorn app.main:app --bind 0.0.0.0:${PORT:-8000} --worker-class uvicorn.workers.UvicornWorker --workers 1 --timeout 0 --access-logfile - --error-logfile -"]
