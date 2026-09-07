FROM python:3.11-slim

LABEL maintainer="mckenna654"
LABEL description="NuvioExporter: Nuvio collection transfer for Fusion and Remux"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gosu \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app/ ./app/
COPY run.py .
COPY docker-entrypoint.sh /usr/local/bin/nuvioexporter-entrypoint

RUN groupadd --system --gid 10001 nuvioexporter \
    && useradd --system --uid 10001 --gid nuvioexporter --create-home nuvioexporter \
    && chmod 755 /usr/local/bin/nuvioexporter-entrypoint

# Environment variables
ENV PORT=7088
ENV HOST=0.0.0.0
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV NUVIOEXPORTER_DATA_DIR=/data
VOLUME ["/data"]

# Expose default port
EXPOSE 7088

# Healthcheck dynamically checking PORT
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:${PORT:-7088}/api/health || exit 1

# Start server using python runner
ENTRYPOINT ["/usr/local/bin/nuvioexporter-entrypoint"]
CMD ["python", "run.py"]
