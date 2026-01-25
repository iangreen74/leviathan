# Worker Dockerfile for GHCR
FROM python:3.10-slim

WORKDIR /app

# Install git (required for cloning repos)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY leviathan/ ./leviathan/

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Create workspace directory
RUN mkdir -p /workspace

# Run worker
ENTRYPOINT ["python", "-m", "leviathan.executor.worker"]
