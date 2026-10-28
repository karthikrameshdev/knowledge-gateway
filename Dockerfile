FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 KNOWLEDGE_GATEWAY_CONFIG=/app/config.example.yaml
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
RUN useradd --system --uid 10001 --create-home gateway
COPY --chown=gateway:gateway src src
COPY --chown=gateway:gateway models/reranker.onnx models/reranker.onnx
COPY --chown=gateway:gateway config.example.yaml .
COPY --chown=gateway:gateway data data
USER gateway
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"
CMD ["python", "-m", "uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8080"]
