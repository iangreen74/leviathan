# Worker Dockerfile for GHCR
FROM python:3.10-slim

WORKDIR /app

# Install git (required for cloning repos) and kubectl (required for scheduler job submission)
# kubectl v1.30.6 matches kind cluster v1.30.0
RUN apt-get update && \
    apt-get install -y --no-install-recommends git curl ca-certificates && \
    curl -L -o /usr/local/bin/kubectl https://dl.k8s.io/release/v1.30.6/bin/linux/amd64/kubectl && \
    chmod +x /usr/local/bin/kubectl && \
    kubectl version --client=true && \
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
