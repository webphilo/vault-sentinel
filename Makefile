.PHONY: install dev run test lint fmt keygen data train replay docker up down

install:
	pip install -e ".[redis]"

dev:
	pip install -e ".[redis,dev]" && pre-commit install

run:
	SENTINEL_DEV_MODE=true sentinel serve --port 8080

test:
	pytest -q

lint:
	ruff check sentinel tests && mypy sentinel

fmt:
	ruff format sentinel tests && ruff check --fix sentinel tests

keygen:
	sentinel keygen

data:
	sentinel gen-data data/history.csv -n 20000

train: data
	sentinel train data/history.csv

replay:
	sentinel replay-incident

docker:
	docker build -t vault-sentinel:latest .

up:
	docker compose up -d --build

down:
	docker compose down
