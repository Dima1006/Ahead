FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -r -u 10001 app
COPY app ./app
USER app
# Needs DATABASE_URL (PostgreSQL).
EXPOSE 8000
# One worker: Telegram polling must run only once (several workers need the webhook mode).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--ws-max-size", "1024"]
