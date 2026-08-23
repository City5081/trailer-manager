FROM python:3.12-slim

LABEL org.opencontainers.image.title="Trailer DE" \
      org.opencontainers.image.description="Traegt deutsche TMDB-Trailer in die NFO-Dateien einer Emby-Bibliothek ein" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/config \
    MOVIES_DIR=/movies \
    PORT=8080 \
    PUID=99 \
    PGID=100

# ca-certificates ist Pflicht: ohne die Wurzelzertifikate schlaegt jede
# HTTPS-Anfrage an TMDB fehl. gosu gibt die Rechte beim Start ab.
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
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
  CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
# Ein einzelner Worker mit Threads: der Zeitplan darf nur einmal laufen.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 8 \
     --timeout 300 --access-logfile - 'main:create_app()'"]
