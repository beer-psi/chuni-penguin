ARG PYTHON_VERSION=3.13

FROM ghcr.io/astral-sh/uv:0.8.22-python${PYTHON_VERSION}-alpine AS builder
ENV PYTHONOPTIMIZE=1 PYTHONNODEBUGRANGES=1 UV_LINK_MODE=copy

# Disable Python downloads, because we want to use the system interpreter
# across both images. If using a managed Python version, it needs to be
# copied from the build image into the final image; see `standalone.Dockerfile`
# for an example.
ENV UV_PYTHON_DOWNLOADS=0

# for building faust-cchardet
RUN apk --update-cache upgrade \
    && apk add --no-interactive build-base pkgconf git rust cargo opus-dev openssl-dev libgcc \
    && apk cache purge \
    && rm -rf /var/cache/apk/*

WORKDIR /code
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/git/db \
    --mount=type=cache,target=/root/.cargo/registry/cache \
    --mount=type=cache,target=/root/.cargo/registry/index \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-install-workspace --all-extras --no-dev --no-group test
COPY . /code
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/git/db \
    --mount=type=cache,target=/root/.cargo/registry/cache \
    --mount=type=cache,target=/root/.cargo/registry/index \
    uv sync --frozen --all-extras --no-dev --no-group test
RUN python -m compileall -b -x 'database/alembic/versions' . \
    && find . -type f -not -path "*database/alembic/versions*" -name '*.py' -exec rm {} \;
RUN rm -rf packages/penguin-native/target

FROM python:${PYTHON_VERSION}-alpine

# Needed for fixing permissions of files created by Docker:
ARG UID=1000
ARG GID=1000

ARG GIT_SHA=unknown

RUN apk --update-cache upgrade \
    && apk add --no-interactive mimalloc opus libssl3 libcrypto3 libgcc patch \
    && apk cache purge \
    && rm -rf /var/cache/apk/*

RUN --mount=type=bind,source=patches/python3-musl-find-library.patch,target=python3-musl-find-library.patch \
    patch "/usr/local/lib/python${PYTHON_VERSION}/ctypes/util.py" python3-musl-find-library.patch

RUN addgroup -g "${GID}" bot \
    && adduser -D -h "/code" -G bot -u "${UID}" bot

COPY --from=builder --chown=bot:bot /code /code

ENV PATH="/code/.venv/bin:$PATH"
ENV GIT_SHA="$GIT_SHA"
ENV LD_PRELOAD="/usr/lib/libmimalloc.so.2"
ENV PYTHONOPTIMIZE=1 PYTHONNODEBUGRANGES=1

USER bot

RUN mkdir -p /code/.cache

WORKDIR /code
ENTRYPOINT ["/code/.venv/bin/python3", "bot.pyc"]
