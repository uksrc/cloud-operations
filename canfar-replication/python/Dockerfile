# FROM python:3.15.2-alpine3.24
# WORKDIR /app

# COPY ../requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# COPY main.py .
# COPY config.py .

# CMD ["python3", "main.py"]

# Stage 1: Build
FROM alpine:3.20 AS builder

ARG PYTHON_VERSION=3.12.4

RUN apk add --no-cache --virtual .build-deps \
    wget \
    gcc \
    make \
    musl-dev \
    zlib-dev \
    libffi-dev \
    openssl-dev \
    bzip2-dev \
    xz-dev \
    readline-dev \
    sqlite-dev \
    ncurses-dev

RUN cd /opt \
    && wget https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz \
    && tar xzf Python-${PYTHON_VERSION}.tgz \
    && cd Python-${PYTHON_VERSION} \
    && ./configure --prefix=/opt/python --with-ensurepip=install \
    && make -j $(nproc) \
    && make install \
    && /opt/python/bin/pip3 --version

# Stage 2: Final
FROM alpine:3.20
ENV PATH="/opt/python/bin:$PATH"
# Only runtime shared libraries
RUN apk add --no-cache \
    libffi \
    openssl \
    zlib \
    bzip2 \
    xz \
    readline \
    sqlite \
    ncurses

COPY --from=builder /opt/python /opt/python
COPY ../requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY main.py .
COPY config.py .



CMD ["python3", "main.py"]