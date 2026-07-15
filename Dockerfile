FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/tarzan

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini wsgi.py ./
COPY migrations ./migrations
COPY app ./app

RUN useradd --create-home tarzan \
    && mkdir -p /data \
    && chown -R tarzan:tarzan /data /srv/tarzan
USER tarzan

ENV TARZAN_DATA_DIR=/data
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=4 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# Apply migrations, then serve with Gunicorn.
CMD ["sh", "-c", "alembic upgrade head && exec gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 8 wsgi:application"]
