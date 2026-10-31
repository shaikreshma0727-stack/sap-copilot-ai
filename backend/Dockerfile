# Slim demo image. Build context is the REPOSITORY ROOT (not backend/):
#   docker build -f backend/Dockerfile -t sap-copilot-ai .
# Knowledge search (RAG) and abaplint are switched off here to fit a 512 MB free instance.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KB_DIR=/srv/knowledge_base \
    RAG_ENABLED=false \
    ABAPLINT_ENABLED=false

WORKDIR /srv/backend

COPY backend/requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY backend/app ./app
COPY knowledge_base/catalog /srv/knowledge_base/catalog
COPY knowledge_base/interview /srv/knowledge_base/interview
COPY knowledge_base/errors /srv/knowledge_base/errors

EXPOSE 8000
# Render sets PORT; locally it falls back to 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
