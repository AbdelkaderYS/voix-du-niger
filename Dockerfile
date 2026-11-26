FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY examples ./examples
COPY scripts ./scripts
COPY docs ./docs
COPY README.md START_HERE.md TRAINING_GUIDE.md ./
ENV ZARMA_DATA_DIR=/data
RUN groupadd --system --gid 10001 voix && useradd --system --uid 10001 --gid voix --no-create-home --shell /usr/sbin/nologin voix && mkdir -p /data && chown -R voix:voix /data
USER voix
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
