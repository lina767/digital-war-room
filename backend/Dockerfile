# Backend for Digital War Room – run from repo root with: docker build -f backend/Dockerfile backend
# On Railway: set Root Directory to "backend" and use Docker builder (this file).
FROM python:3.12-slim

WORKDIR /app

# Install dependencies (no secrets in image; use env at runtime)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# PORT is set by Railway at runtime
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
