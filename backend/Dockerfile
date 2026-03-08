# Use Python 3.12 slim bookworm image (lightweight and stable)
FROM python:3.12-slim-bookworm

# Install curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git && rm -rf /var/lib/apt/lists/*

# Install uv using the official installer script (recommended method)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /bin/uv && \
    chmod +x /bin/uv

# Set working directory
WORKDIR /app

# Copy only dependency files first (maximizes layer caching)
COPY pyproject.toml uv.lock* ./

# Install production dependencies only (no dev/notebook deps)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev --frozen

# Copy application code
COPY . .

# Install the project itself (fast, just links the local package)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen

# Make entrypoint script executable
RUN chmod +x entrypoint.sh

# Expose port 8000
EXPOSE 8000

# Use entrypoint script for flexible startup (supports hot reload)
ENTRYPOINT ["/app/entrypoint.sh"]

