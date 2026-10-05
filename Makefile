# Every target is a thin wrapper around a `uv run radar <command>` entry point,
# so the project works the same without Make installed.

.PHONY: up down migrate audit backfill test lint demo

up:
	uv run radar up

down:
	uv run radar down

migrate:
	uv run radar migrate

audit:
	uv run radar audit

backfill:
	uv run radar backfill

test:
	uv run radar test

lint:
	uv run radar lint

demo:
	uv run radar demo
