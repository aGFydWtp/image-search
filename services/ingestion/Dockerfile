FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir . && rm -rf /root/.cache

COPY shared/ ./shared/
COPY services/ingestion/ ./services/ingestion/

CMD ["python", "-m", "services.ingestion.run"]
