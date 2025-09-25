# API Gateway Dockerfile
FROM python:3.13.7-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SERVICE_PORT=8000 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libc6-dev \
    libffi-dev \
    libssl-dev \
    make \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set work directory
WORKDIR /app

# Copy requirements first for better caching
COPY api_gateway/requirements.txt ./requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy API Gateway application code
COPY api_gateway/ ./api_gateway/

# Copy common directory (shared models and utilities)
COPY common/ ./common/

# Copy keys generation script
COPY generate_keys.py ./generate_keys.py

# Copy startup script
COPY api_gateway/startup.sh ./startup.sh

# Create necessary directories and set permissions
RUN mkdir -p /app/logs /app/keys && \
    chmod +x /app/startup.sh && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Start the API Gateway
CMD ["/app/startup.sh"]