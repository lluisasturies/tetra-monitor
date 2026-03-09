# ==============================
#   TETRA Monitor — Makefile
# ==============================

PROJECT_ROOT := $(shell pwd)
SERVICE_NAME := tetra-monitor
SERVICE_FILE := $(PROJECT_ROOT)/scripts/tetra-monitor.service
SERVICE_DEST := /etc/systemd/system/$(SERVICE_NAME).service

.PHONY: help setup start stop restart logs install-service uninstall-service update status

help:
	@echo ""
	@echo "  TETRA Monitor — comandos disponibles"
	@echo ""
	@echo "  make setup              Instala dependencias y prepara el entorno"
	@echo "  make start              Arranca el monitor en primer plano"
	@echo "  make stop               Detiene el servicio systemd"
	@echo "  make restart            Reinicia el servicio systemd"
	@echo "  make status             Muestra el estado del servicio systemd"
	@echo "  make logs               Muestra los logs en tiempo real"
	@echo "  make install-service    Instala tetra-monitor como servicio systemd"
	@echo "  make uninstall-service  Elimina el servicio systemd"
	@echo "  make update             git pull + reinicia el servicio"
	@echo ""

setup:
	sudo bash scripts/setup.sh

start:
	bash scripts/start.sh

stop:
	sudo systemctl stop $(SERVICE_NAME)

restart:
	sudo systemctl restart $(SERVICE_NAME)

status:
	sudo systemctl status $(SERVICE_NAME)

logs:
	sudo journalctl -u $(SERVICE_NAME) -f --output=cat

install-service:
	sudo cp $(SERVICE_FILE) $(SERVICE_DEST)
	sudo systemctl daemon-reload
	sudo systemctl enable $(SERVICE_NAME)
	@echo "Servicio instalado. Arranca con: make start-service o sudo systemctl start $(SERVICE_NAME)"

uninstall-service:
	sudo systemctl stop $(SERVICE_NAME) || true
	sudo systemctl disable $(SERVICE_NAME) || true
	sudo rm -f $(SERVICE_DEST)
	sudo systemctl daemon-reload
	@echo "Servicio eliminado"

update:
	git pull
	sudo systemctl restart $(SERVICE_NAME)
	@echo "Actualización completada"