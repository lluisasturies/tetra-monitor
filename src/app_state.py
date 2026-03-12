from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db.pool import DBPool
    from db.llamadas import LlamadasDB
    from db.grupos import GruposDB
    from integrations.telegram_bot import TelegramBot
    from integrations.email_notifier import EmailNotifier
    from core.afiliacion import AfiliacionConfig
    from filters.keyword_filter import KeywordFilter


class AppState:
    """Contenedor de dependencias compartidas entre main.py y la API."""

    def __init__(self):
        self.pool: DBPool | None = None
        self.llamadas: LlamadasDB | None = None
        self.grupos: GruposDB | None = None
        self.bot: TelegramBot | None = None
        self.email: EmailNotifier | None = None
        self.afiliacion: AfiliacionConfig | None = None
        self.keyword_filter: KeywordFilter | None = None
        # FIX: refresh_tokens como atributo de instancia para evitar que
        # multiples instancias de AppState compartan el mismo set.
        self.refresh_tokens: set[str] = set()
        self.radio_connected: bool = False
        self.streaming_active: bool = False


app_state = AppState()
