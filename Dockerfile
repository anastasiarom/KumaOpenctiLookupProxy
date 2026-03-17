FROM python:3.14.3-alpine3.23

RUN apk update && apk add --no-cache \
    build-base \
    curl

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--workers", "18", "--bind", "0.0.0.0:8000", "--log-level", "info"]
