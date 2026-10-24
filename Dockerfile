# RESTARTION server — dari-nol transformer (58.75M params) + akun asli, port 4006
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# torch CPU dulu (wheel kecil dari index cpu), sisanya dari PyPI
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir flask tokenizers numpy werkzeug

COPY . .

# DATA_DIR: tempat db + memori AI per-akun (volume). PORT: default 4006 (boss spec)
ENV PORT=4006 \
    DATA_DIR=/data \
    TORCH_THREADS=2

EXPOSE 4006
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:4006/api/health', timeout=4).status==200 else 1)"

CMD ["python", "server.py"]
