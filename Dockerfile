# dev-news-bot — Raspberry Pi / ARM compatible (Portainer)
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application
COPY bot.py .

# Non-root user and data dir for persisted state (mount volume on /data in Portainer)
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser /app \
    && mkdir /data && chown appuser /data
USER appuser

ENV SEEN_PATH=/data/seen.json

CMD ["python", "-u", "bot.py"]
