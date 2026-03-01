# --- build frontend ---
FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- backend runtime ---
FROM python:3.11-slim AS backend
WORKDIR /app

# system deps for lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libxml2-dev libxslt1-dev \
  && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
RUN touch ./backend/__init__.py  
COPY --from=frontend /frontend/dist /app/frontend/dist

ENV FRONTEND_DIST=/app/frontend/dist
ENV PYTHONPATH=/app/backend

# Zeabur will set PORT; fallback for local docker
ENV PORT=8080

CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8080} --log-level debug --access-log"]
