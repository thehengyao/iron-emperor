FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 openscad && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source
COPY src/ src/
COPY run.py run_staged.py ./

# Frontend build artifacts
COPY --from=frontend /app/frontend/dist frontend/dist

# Database (mount or copy)
# COPY parts.db .

EXPOSE 8000
ENV PYTHONPATH=/app
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
