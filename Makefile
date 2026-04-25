.PHONY: help up down build logs restart reset status

# Цвета для вывода
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m

help: ## Показать справку
	@echo "$(GREEN)NeoMarket Backend - Docker команды:$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*?##/ { printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""

up: ## Запустить все сервисы (БД + B2B + B2C + Moderation)
	@echo "$(GREEN)Запускаю все сервисы...$(NC)"
	docker compose up --build -d
	@echo ""
	@echo "$(GREEN)✅ Сервисы запущены:$(NC)"
	@echo "  B2B:        http://localhost:8001/docs"
	@echo "  B2C:        http://localhost:8002/docs"
	@echo "  Moderation: http://localhost:8003/docs"
	@echo "  PostgreSQL: localhost:5432"
	@echo ""
	@echo "Логи: $(YELLOW)make logs$(NC)"

down: ## Остановить все сервисы
	@echo "$(YELLOW)Останавливаю сервисы...$(NC)"
	docker compose down
	@echo "$(GREEN)✅ Сервисы остановлены$(NC)"

build: ## Пересобрать Docker образы
	@echo "$(GREEN)Пересобираю образы...$(NC)"
	docker compose build
	@echo "$(GREEN)✅ Образы пересобраны$(NC)"

logs: ## Показать логи всех сервисов
	docker compose logs -f

restart: ## Перезапустить все сервисы
	@echo "$(YELLOW)Перезапускаю сервисы...$(NC)"
	docker compose restart
	@echo "$(GREEN)✅ Сервисы перезапущены$(NC)"

reset: ## Полностью удалить все (контейнеры + данные)
	@echo "$(RED)⚠️  ВНИМАНИЕ: Все данные будут удалены!$(NC)"
	@read -p "Продолжить? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker compose down -v; \
		echo "$(GREEN)✅ Все удалено$(NC)"; \
	fi

status: ## Показать статус контейнеров
	@docker compose ps

.DEFAULT_GOAL := help
