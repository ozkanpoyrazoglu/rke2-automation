.PHONY: help up down logs shell-backend shell-frontend clean

help:
	@echo "RKE2 Automation - Available Commands"
	@echo ""
	@echo "  make up              Start all services"
	@echo "  make down            Stop all services"
	@echo "  make logs            View logs"
	@echo "  make shell-backend   Open backend shell"
	@echo "  make shell-frontend  Open frontend shell"
	@echo "  make clean           Remove data and artifacts"

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

shell-backend:
	docker-compose exec backend /bin/bash

shell-frontend:
	docker-compose exec frontend /bin/sh

clean:
	rm -rf data/
	rm -rf ansible/clusters/*
	rm -rf ansible/artifacts/
