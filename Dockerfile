FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV WORKER_ID=worker-1
ENV POLL_INTERVAL=5
ENV MAX_WORKERS=4
ENV DATABASE_URL=postgresql://worker:worker@db:5432/jobs

EXPOSE 8652

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8652"]
