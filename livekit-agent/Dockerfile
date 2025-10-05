# # Use an official Python runtime as a parent image
# FROM python:3.13.7-slim

# # Set the working directory in the container
# WORKDIR /app

# # Copy the requirements file and install dependencies
# # This is cached to speed up builds if requirements don't change
# COPY livekit-agent/requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# # Copy only the agent's application code into the container
# COPY livekit-agent/ .

# # Make startup script executable
# RUN chmod +x startup.sh

# # Expose the port that Cloud Run expects
# EXPOSE 8080

# # Set environment variable for PORT (Cloud Run will override this)
# ENV PORT=8080

# # Command to run the agent server with health check endpoint
# CMD ["python", "-u", "server.py", "start"]


# Multi-Tenant LiveKit Agent Dockerfile
# Optimized for handling multiple concurrent sessions

FROM python:3.13.7-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    ffmpeg \
    libopus0 \
    libopus-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for layer caching)
COPY livekit-agent/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY livekit-agent/ /app/

# Create non-root user for security
RUN useradd -m -u 1000 agentuser && chown -R agentuser:agentuser /app
USER agentuser

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Expose port
EXPOSE 8080

# Run the multi-tenant server
CMD ["python", "server.py", "start"]
