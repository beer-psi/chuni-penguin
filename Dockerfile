ARG PYTHON_BUILD_VERSION=3.13

FROM ghcr.io/astral-sh/uv:0.10.6-python${PYTHON_BUILD_VERSION}-alpine AS builder
ENV PYTHONOPTIMIZE=1 PYTHONNODEBUGRANGES=1 UV_LINK_MODE=copy

# Disable Python downloads, because we want to use the system interpreter
# across both images. If using a managed Python version, it needs to be
# copied from the build image into the final image; see `standalone.Dockerfile`
# for an example.
ENV UV_PYTHON_DOWNLOADS=0

# for building penguin-native
RUN apk --update-cache upgrade \
    && apk add --no-interactive rust cargo git \
    && apk cache purge \
    && rm -rf /var/cache/apk/*

WORKDIR /code
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/git/db \
    --mount=type=cache,target=/root/.cargo/registry/cache \
    --mount=type=cache,target=/root/.cargo/registry/index \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-install-workspace --all-extras --no-dev --no-group test --no-group docs
COPY . /code
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/git/db \
    --mount=type=cache,target=/root/.cargo/registry/cache \
    --mount=type=cache,target=/root/.cargo/registry/index \
    uv sync --frozen --all-extras --no-dev --no-group test --no-group docs
RUN rm -rf packages/penguin-native/target
RUN python -m compileall -b -x 'database/alembic/versions' . \
    && find . -type f -not -path "*database/alembic/versions*" -name '*.py' -exec rm {} \;

FROM python:${PYTHON_BUILD_VERSION}-alpine
ARG PYTHON_BUILD_VERSION

# Needed for fixing permissions of files created by Docker:
ARG UID=1000
ARG GID=1000

ARG GIT_SHA=unknown

RUN apk --update-cache upgrade \
    && apk add --no-interactive mimalloc opus libgcc libmagic patch libwebp git \
    && apk cache purge \
    && rm -rf /var/cache/apk/*

RUN --mount=type=bind,source=patches/python3-musl-find-library.patch,target=python3-musl-find-library.patch \
    patch "/usr/local/lib/python${PYTHON_BUILD_VERSION}/ctypes/util.py" python3-musl-find-library.patch

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
ENTRYPOINT ["/code/.venv/bin/python3", "launcher.pyc"]
