# Control Plane API Dockerfile for GHCR
FROM python:3.10-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY leviathan/ ./leviathan/

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose API port
EXPOSE 8000

# Run control plane API
ENTRYPOINT ["python", "-m", "leviathan.control_plane.api"]
