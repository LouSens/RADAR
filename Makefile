# Every target is a thin wrapper around a `uv run radar <command>` entry point,
# so the project works the same without Make installed.

.PHONY: up down migrate audit backfill quality test lint demo

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

quality:
	uv run radar quality

test:
	uv run radar test

lint:
	uv run radar lint

demo:
	uv run radar demo
