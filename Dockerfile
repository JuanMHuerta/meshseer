FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV MESHSEER_BIND_HOST=0.0.0.0
ENV MESHSEER_BIND_PORT=8000
ENV MESHSEER_DB_PATH=/data/meshseer.db

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin meshseer &&     mkdir -p /data &&     chown -R meshseer:meshseer /data /app

COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md /app/
COPY src /app/src

RUN python -m pip install --upgrade pip &&     python -m pip install .

USER meshseer

VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"]

CMD ["meshseer"]
