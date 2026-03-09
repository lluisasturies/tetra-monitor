from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db.pool import DBPool
    from db.llamadas import LlamadasDB
    from db.grupos import GruposDB
    from integrations.telegram_bot import TelegramBot
    from core.afiliacion import AfiliacionConfig


class AppState:
    """Contenedor de dependencias compartidas entre main.py y la API."""
    pool: DBPool | None = None
    llamadas: LlamadasDB | None = None
    grupos: GruposDB | None = None
    bot: TelegramBot | None = None
    afiliacion: AfiliacionConfig | None = None
    refresh_tokens: set[str] = set()  # tokens válidos en memoria


app_state = AppState()
