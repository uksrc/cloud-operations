# psusdev/gitlab-cicd:v0.16
#
# Drafted in ansible-infinidat-collection but belongs in the psusdev/gitlab-cicd
# image source repo. Move before tagging/pushing.
#
# Replaces v0.15 (Ubuntu 22.04, Python 3.10) — bumped to Ubuntu 24.04 for
# Python 3.12, the controller minimum for ansible-core 2.18+.

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-dev \
        python3-pip \
        build-essential \
        libffi-dev \
        libssl-dev \
        git \
        curl \
        ca-certificates \
        jq \
 && rm -rf /var/lib/apt/lists/*

ARG SPRUCE_VERSION=1.31.1
RUN curl -fsSL -o /usr/local/bin/spruce \
        "https://github.com/geofffranks/spruce/releases/download/v${SPRUCE_VERSION}/spruce-linux-amd64" \
 && chmod +x /usr/local/bin/spruce

RUN python3 --version \
 && pip3 --version \
 && git --version \
 && jq --version \
 && spruce --version
