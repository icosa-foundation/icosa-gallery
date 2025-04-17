# syntax=docker/dockerfile:1

####
# Dependencies builder
####
FROM python:3.13.3-slim AS builder

WORKDIR /opt
ENV LANG=C.UTF-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/venv/bin:$PATH"

# Install build dependencies
RUN set -x \
    && BUILD_DEPS=" \
    build-essential \
    libmagic-dev \
    libpq-dev \
    nodejs \
    npm \
    " \
    && apt-get update \
    && apt-get install -y --no-install-recommends $BUILD_DEPS

# npm packages setup
COPY package.json .
RUN npm install

# Virtualenv setup
RUN python -m venv /venv
COPY requirements.in .
RUN pip install --no-cache-dir -r requirements.in

####
# Slim app container
####
FROM python:3.13.3-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PATH="/venv/bin:$PATH"

# Install app dependencies
RUN set -x \
    && BUILD_DEPS=" \
    git \
    libpq-dev \
    libmagic-dev \
    htop \
    nodejs \
    " \
    && apt-get update \
    && apt-get install -y --no-install-recommends $BUILD_DEPS

WORKDIR /opt
EXPOSE 8001

COPY --from=builder /venv /venv
COPY --from=builder /opt/node_modules /node_modules
COPY . .

RUN mkdir -p /opt/logs

ENTRYPOINT [ "./entrypoint.sh" ]
