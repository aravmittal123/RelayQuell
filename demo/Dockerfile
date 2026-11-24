FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.165.0 uvicorn==0.54.0 httpx==0.28.1
COPY . .
USER 10001
