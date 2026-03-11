# ==============================
#   TETRA Monitor — Makefile
# ==============================

PROJECT_ROOT  := $(shell pwd)
SERVICE_NAME  := tetra-monitor
SERVICE_TMPL  := $(PROJECT_ROOT)/scripts/tetra-monitor.service.template
SERVICE_DEST  := /etc/systemd/system/$(SERVICE_NAME).service
CURRENT_USER  := $(shell logname 2>/dev/null || echo $$SUDO_USER || echo $$USER)

CONFIG_FILES := \
	config/config.yaml \
	config/keywords.yaml \
	config/afiliacion.yaml \
	config/grupos.yaml

.PHONY: help init setup setup-https set-password start stop restart logs logs-file \
        install-service uninstall-service update status reload-grupos backup-db \
        test lint

help:
	@echo ""
	@echo "  TETRA Monitor — comandos disponibles"
	@echo ""
	@echo "  make init               Copia todos los ficheros .example a su config local"
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
	@echo "  make update             git pull + reinicia el servicio si esta activo"
	@echo "  make reload-grupos      Recarga el catalogo desde config/grupos.yaml"
	@echo "  make backup-db          Volcado de la BD en data/backups/"
	@echo "  make test               Ejecuta todos los tests con pytest"
	@echo "  make lint               Comprueba el estilo con ruff"
	@echo ""

init:
	@echo "Copiando ficheros de configuracion..."
	@for f in $(CONFIG_FILES); do \
		example=$${f%.yaml}.yaml.example; \
		if [ -f "$$example" ]; then \
			if [ -f "$$f" ] && grep -qv '^#' "$$f" 2>/dev/null; then \
				echo "  [omitido] $$f ya existe con contenido"; \
			else \
				cp "$$example" "$$f"; \
				echo "  [copiado] $$example -> $$f"; \
			fi; \
		else \
			echo "  [aviso]   no se encontro $$example"; \
		fi; \
	done
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "  [copiado] .env.example -> .env"; \
	else \
		echo "  [omitido] .env ya existe"; \
	fi
	@echo ""
	@echo "Listo. Edita los ficheros de config/ y .env con tus valores reales."
	@echo "A continuacion ejecuta: make setup"

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

reload-grupos:
	$(PROJECT_ROOT)/venv/bin/python3 scripts/reload_grupos.py

backup-db:
	bash scripts/backup_db.sh

test:
	$(PROJECT_ROOT)/venv/bin/pytest tests/ -v

lint:
	$(PROJECT_ROOT)/venv/bin/ruff check src/ tests/
