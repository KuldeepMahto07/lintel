# Lintel, self-hosted: the web app, API and plugin endpoint in one container.
# See docs/self-hosting.md. Pair it with Postgres (docker-compose.yml does).
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY web web
COPY samples samples
COPY hosts hosts

ENV PYTHONUNBUFFERED=1
EXPOSE 8002
USER nobody
CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8002", "--proxy-headers", "--forwarded-allow-ips", "*"]
