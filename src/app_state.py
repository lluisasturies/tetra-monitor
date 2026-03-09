from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db.pool import DBPool
    from db.llamadas import LlamadasDB
    from integrations.telegram_bot import TelegramBot


class AppState:
    """Contenedor de dependencias compartidas entre main.py y la API."""
    pool: DBPool | None = None
    llamadas: LlamadasDB | None = None
    bot: TelegramBot | None = None


app_state = AppState()
