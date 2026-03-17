FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir . && rm -rf /root/.cache

COPY shared/ ./shared/
COPY services/search/ ./services/search/
COPY services/__init__.py ./services/__init__.py
COPY services/ingestion/ ./services/ingestion/

EXPOSE 8000

CMD ["uvicorn", "services.search.app:app", "--host", "0.0.0.0", "--port", "8000"]
