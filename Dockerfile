FROM python:3.11-slim

# Install OpenSSL for certificate generation
RUN apt-get update && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server.py .
COPY conversation.py .
COPY validation.py .
COPY session_manager.py .
COPY audio_streamer.py .
COPY metrics.py .
COPY generate-cert.sh .
COPY static/ ./static/

# Generate SSL certificate
RUN chmod +x /app/generate-cert.sh && /app/generate-cert.sh

# Health check — try HTTPS first, fall back to HTTP
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,ssl; ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE; urllib.request.urlopen('https://localhost:7100/health', context=ctx)" || python -c "import urllib.request; urllib.request.urlopen('http://localhost:7101/health')" || exit 1

# Expose both HTTPS (primary) and HTTP (fallback) ports
EXPOSE 7100 7101

CMD ["python", "server.py"]
