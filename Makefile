# ==============================
#   TETRA Monitor — Makefile
# ==============================

PROJECT_ROOT  := $(shell pwd)
SERVICE_NAME  := tetra-monitor
SERVICE_TMPL  := $(PROJECT_ROOT)/scripts/tetra-monitor.service.template
SERVICE_DEST  := /etc/systemd/system/$(SERVICE_NAME).service
CURRENT_USER  := $(shell logname 2>/dev/null || echo $$SUDO_USER || echo $$USER)

.PHONY: help setup setup-https set-password start stop restart logs install-service uninstall-service update status

help:
	@echo ""
	@echo "  TETRA Monitor — comandos disponibles"
	@echo ""
	@echo "  make setup              Instala dependencias y prepara el entorno"
	@echo "  make setup-https        Instala nginx con TLS (certificado autofirmado)"
	@echo "  make set-password       Genera hash bcrypt y lo guarda en .env"
	@echo "  make start              Arranca el monitor en primer plano"
	@echo "  make stop               Detiene el servicio systemd"
	@echo "  make restart            Reinicia el servicio systemd"
	@echo "  make status             Muestra el estado del servicio systemd"
	@echo "  make logs               Muestra los logs en tiempo real (journalctl)"
	@echo "  make logs-file          Muestra los logs en tiempo real (fichero)"
	@echo "  make install-service    Instala tetra-monitor como servicio systemd"
	@echo "  make uninstall-service  Elimina el servicio systemd"
	@echo "  make update             git pull + reinicia el servicio si está activo"
	@echo ""

setup:
	sudo bash scripts/setup.sh

setup-https:
	sudo bash scripts/setup_nginx.sh

set-password:
	$(PROJECT_ROOT)/venv/bin/python3 scripts/hash_password.py --env $(PROJECT_ROOT)/.env

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

logs-file:
	tail -f $(PROJECT_ROOT)/logs/tetra_monitor.log

install-service:
	@echo "Instalando servicio para usuario '$(CURRENT_USER)' en $(PROJECT_ROOT)..."
	sed \
		-e 's|@@PROJECT_ROOT@@|$(PROJECT_ROOT)|g' \
		-e 's|@@USER@@|$(CURRENT_USER)|g' \
		$(SERVICE_TMPL) | sudo tee $(SERVICE_DEST) > /dev/null
	sudo systemctl daemon-reload
	sudo systemctl enable $(SERVICE_NAME)
	@echo "Servicio instalado. Arranca con: sudo systemctl start $(SERVICE_NAME)"

uninstall-service:
	sudo systemctl stop $(SERVICE_NAME) || true
	sudo systemctl disable $(SERVICE_NAME) || true
	sudo rm -f $(SERVICE_DEST)
	sudo systemctl daemon-reload
	@echo "Servicio eliminado"

update:
	git pull
	@sudo systemctl is-active --quiet $(SERVICE_NAME) && sudo systemctl restart $(SERVICE_NAME) && echo "Servicio reiniciado" || echo "Servicio no activo, omitiendo reinicio"
