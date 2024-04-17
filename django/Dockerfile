# syntax=docker/dockerfile:1

####
# Dependencies builder
####
FROM python:3.11.9-slim as builder

WORKDIR /opt
ENV LANG=C.UTF-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/venv/bin:$PATH"

# Install build dependencies
RUN set -x \
    && BUILD_DEPS=" \
    build-essential \
    libpq-dev \
    " \
    && apt-get update \
    && apt-get install -y --no-install-recommends $BUILD_DEPS

# Virtualenv setup
RUN python -m venv /venv
COPY requirements.in .
RUN pip install --no-cache-dir -r requirements.in

####
# Slim app container
####
FROM python:3.11.9-slim as app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PATH="/venv/bin:$PATH"

# Install app dependencies
RUN set -x \
    && BUILD_DEPS=" \
    git \
    libpq-dev \
    " \
    && apt-get update \
    && apt-get install -y --no-install-recommends $BUILD_DEPS

WORKDIR /opt
EXPOSE 8001

COPY --from=builder /venv /venv
COPY . .

RUN mkdir -p /opt/logs

ENTRYPOINT [ "./entrypoint.sh" ]
