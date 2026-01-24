# Leviathan Worker Dockerfile
# Runs inside K8s Jobs to execute task attempts

FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy leviathan package
COPY leviathan/ ./leviathan/

# Create workspace directory
RUN mkdir -p /workspace

# Set entrypoint
ENTRYPOINT ["python", "-m", "leviathan.executor.worker"]
