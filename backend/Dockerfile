FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN prisma generate

RUN mkdir -p /app/storage/images /app/storage/videos

EXPOSE 8000

CMD ["sh", "-c", "prisma migrate deploy && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
