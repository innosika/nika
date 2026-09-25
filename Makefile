# Короткие команды для запуска NIKA. Всё — обёртки над docker compose.
#   make up      — собрать недостающие образы и поднять систему в фоне, дождаться готовности
#   make down    — остановить
#   make logs    — логи всех сервисов
#   make build   — пересобрать образы (после правок C++ или Dockerfile)
#   make kb      — пересобрать базу знаний и перезапустить problem-solver
#   make status  — состояние контейнеров

COMPOSE := docker compose

.PHONY: up down logs build kb status wait

up:
	$(COMPOSE) up -d --build
	@$(MAKE) --no-print-directory wait

wait:
	@echo "Ожидание готовности problem-solver (сборка БЗ занимает 1–3 минуты)..."
	@for i in $$(seq 1 90); do \
		s=$$(docker inspect -f '{{.State.Health.Status}}' nika-problem-solver 2>/dev/null); \
		if [ "$$s" = "healthy" ]; then break; fi; \
		if [ "$$s" = "unhealthy" ]; then echo "problem-solver unhealthy, см. make logs"; exit 1; fi; \
		sleep 5; \
	done
	@$(COMPOSE) ps
	@echo ""
	@echo "sc-web:           http://localhost:8000"
	@echo "Диалоговый UI:    http://localhost:3033"

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

build:
	$(COMPOSE) build

kb:
	$(COMPOSE) restart problem-solver
	@$(MAKE) --no-print-directory wait

status:
	$(COMPOSE) ps
