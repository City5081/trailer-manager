FROM python:3.12-slim

LABEL org.opencontainers.image.title="Trailer Manager" \
      org.opencontainers.image.description="Writes German TMDB trailers into the NFO files of an Emby library" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/config \
    MOVIES_DIR=/movies \
    PORT=8081 \
    PUID=99 \
    PGID=100

# ca-certificates is required: without the root certificates every HTTPS
# request to TMDB fails. gosu drops privileges at startup.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates tzdata curl gosu \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 100 -o app \
 && useradd -u 99 -g 100 -o -M -d /config -s /usr/sbin/nologin app

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh && mkdir -p /config /movies

VOLUME ["/config"]
EXPOSE 8081

HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
  CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
# A single worker with threads: the schedule must only run once.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 8 \
     --timeout 300 --access-logfile - 'main:create_app()'"]
