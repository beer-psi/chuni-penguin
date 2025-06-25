FROM ghcr.io/astral-sh/uv:0.6.13-python3.12-bookworm AS base

# Needed for fixing permissions of files created by Docker:
ARG UID=1000 \
  GID=1000

ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PYTHONDONTWRITEBYTECODE=1 \
  # pip:
  PIP_NO_CACHE_DIR=1 \
  PIP_DISABLE_PIP_VERSION_CHECK=1 \
  PIP_DEFAULT_TIMEOUT=100 \
  PIP_ROOT_USER_ACTION=ignore

SHELL ["/bin/bash", "-eo", "pipefail", "-c"]  

RUN apt-get update && apt-get upgrade -y \
  && apt-get install --no-install-recommends -y \
  build-essential \
  pkg-config \
  libuv1 \
  curl \
  git \
  ffmpeg \
  # clear out apt cache
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && apt-get clean -y && rm -rf /var/lib/apt/lists/*

WORKDIR /code

RUN groupadd -g "${GID}" -r bot \
  && useradd -d '/code' -g bot -l -r -u "${UID}" bot \
  && chown -R bot:bot '/code'

COPY --chown=bot:bot pyproject.toml uv.lock .python-version /code/

RUN uv sync --frozen --all-extras
RUN uv run pypatch apply patches/discord-py-10210.patch discord

COPY --chown=bot:bot . /code

USER bot
ENTRYPOINT ["/code/.venv/bin/python3", "bot.py"]
