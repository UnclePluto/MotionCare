FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 motioncare \
    && useradd --uid 10001 --gid motioncare --create-home motioncare

WORKDIR /app
COPY backend /app/backend
COPY docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx /app/docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx

RUN python -m pip install --no-cache-dir /app/backend \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R motioncare:motioncare /app

USER motioncare
WORKDIR /app/backend

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "180", "--access-logfile", "-", "--error-logfile", "-"]
