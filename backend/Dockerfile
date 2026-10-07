# syntax=docker/dockerfile:1
#
# CylinGuard API.
#
# python:3.13-slim rather than alpine: scikit-learn, numpy, bcrypt and cryptography all
# publish manylinux wheels, so this image installs them as binaries and needs no compiler.
# On alpine (musl) those same packages have no wheels and the build would pull in gcc,
# gfortran and OpenBLAS - a slower build and a larger image, for a smaller base.
FROM python:3.13-slim AS base

# PYTHONDONTWRITEBYTECODE: .pyc files in a read-only layer are dead weight.
# PYTHONUNBUFFERED: without it, logs sit in a buffer and `docker logs` looks silent during
# a crash, which is exactly when they are needed.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl is for the container healthcheck. Installed before the dependency layer so a
# requirements change does not reinstall it.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/*

# Requirements first, as their own layer: application code changes far more often than
# dependencies, and this keeps the slow pip install cached across code edits.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# The ML artifact is written at runtime by /api/ml/train, so the directory must exist and
# be writable by the non-root user. .dockerignore keeps any locally trained model out of
# the image - a model fitted on someone's laptop should not ship.
RUN mkdir -p app/ml/artifacts \
    && useradd --create-home --uid 10001 cylinguard \
    && chown -R cylinguard:cylinguard /app
USER cylinguard

EXPOSE 8000

# Hits the app's own /health, which checks the database too - so an unhealthy mark means
# the service genuinely cannot serve, not merely that the process is alive.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
