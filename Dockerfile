FROM ghcr.io/astral-sh/uv:0.7.19-python3.13-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Disable Python downloads, because we want to use the system interpreter
# across both images. If using a managed Python version, it needs to be
# copied from the build image into the final image; see `standalone.Dockerfile`
# for an example.
ENV UV_PYTHON_DOWNLOADS=0

# for building faust-cchardet
RUN apt-get update && apt-get upgrade --yes \
    && apt-get install --no-install-recommends --yes build-essential pkg-config \
    # clear out apt cache
    && apt-get purge --yes --auto-remove --option APT::AutoRemove::RecommendsImportant=false \
    && apt-get clean --yes && rm --recursive --force /var/lib/apt/lists/*

WORKDIR /code
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --all-extras --no-dev --no-group test
RUN --mount=type=bind,source=patches,target=patches \
    /code/.venv/bin/pypatch apply patches/discord-py-10210.patch discord
COPY . /code
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --all-extras --no-dev --no-group test

FROM python:3.13-slim-bookworm

# Needed for fixing permissions of files created by Docker:
ARG UID=1000
ARG GID=1000

ARG GIT_SHA=unknown

RUN apt-get update && apt-get upgrade --yes \
    && apt-get install --no-install-recommends --yes ffmpeg \
    # clear out apt cache
    && apt-get purge --yes --auto-remove --option APT::AutoRemove::RecommendsImportant=false \
    && apt-get clean --yes && rm --recursive --force /var/lib/apt/lists/*

RUN groupadd --gid "${GID}" bot \
    && useradd --home '/code' --gid bot --no-log-init --uid "${UID}" bot

COPY --from=builder --chown=bot:bot /code /code

ENV PATH="/code/.venv/bin:$PATH"
ENV GIT_SHA="$GIT_SHA"

USER bot
WORKDIR /code
ENTRYPOINT ["/code/.venv/bin/python3", "bot.py"]
