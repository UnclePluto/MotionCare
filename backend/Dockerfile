FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg libreoffice-writer fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 motioncare \
    && useradd --uid 10001 --gid motioncare --create-home motioncare

WORKDIR /app
COPY packages/motion_analysis_contract /app/packages/motion_analysis_contract
COPY ["backend/requirements.lock.txt", "/app/backend/requirements.lock.txt"]
RUN python -m pip install --no-cache-dir -r /app/backend/requirements.lock.txt \
    && python -m pip install --no-cache-dir setuptools==80.9.0 wheel==0.45.1 \
    && python -m pip install --no-cache-dir --no-deps --no-build-isolation /app/packages/motion_analysis_contract

COPY backend /app/backend
COPY specs/patient-rehab-system/crf /app/specs/patient-rehab-system/crf
COPY docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx /app/docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx

COPY scripts/verify_crf_release.py /app/scripts/verify_crf_release.py
COPY scripts/crf_registry /app/scripts/crf_registry
COPY frontend/src/crf/registry.v1.json /app/frontend/src/crf/registry.v1.json

RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation /app/backend \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R motioncare:motioncare /app

USER motioncare
WORKDIR /app/backend
RUN python manage.py check_crf_assets \
    && python /app/scripts/verify_crf_release.py

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "180", "--access-logfile", "-", "--error-logfile", "-"]
