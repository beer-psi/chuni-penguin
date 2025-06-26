set export

PYTHONUTF8 := "1"
PYTHONIOENCODING := "utf-8"

default:
    @just --choose

dev:
    uv run jurigged bot.py

dbutils *ARGS:
    @uv run python -m dbutils {{ARGS}}