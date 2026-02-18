FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server.py .
COPY conversation.py .
COPY static/ ./static/

# Health check — curl isn't in slim, use python
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7100/health')" || exit 1

EXPOSE 7100

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7100"]
