FROM python:3.10-slim

WORKDIR /app

# Install only console dependencies (no git, no kubectl)
RUN pip install --no-cache-dir \
    fastapi>=0.100.0 \
    uvicorn>=0.23.0 \
    httpx>=0.25.0 \
    pydantic>=2.0.0

# Copy only the operator_console module and minimal dependencies
COPY leviathan/__init__.py ./leviathan/
COPY leviathan/operator_console/ ./leviathan/operator_console/

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

ENTRYPOINT ["python3", "-m", "leviathan.operator_console.api"]
