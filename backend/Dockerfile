# Use Python 3.12 slim bookworm image (lightweight and stable)
FROM python:3.12-slim-bookworm

# Install curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*

# Install uv using the official installer script (recommended method)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /bin/uv && \
    chmod +x /bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files and package structure needed for build
COPY pyproject.toml uv.lock* ./
COPY lab_tutor_backend/ ./lab_tutor_backend/

# Install dependencies using uv sync (will create venv and install deps)
RUN uv sync --no-cache

# Copy application code
COPY . .

# Make entrypoint script executable
RUN chmod +x entrypoint.sh

# Expose port 8000
EXPOSE 8000

# Use entrypoint script for flexible startup (supports hot reload)
ENTRYPOINT ["/app/entrypoint.sh"]

