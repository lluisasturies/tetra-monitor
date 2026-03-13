class AppState:
    """
    Estado global compartido entre el daemon PEI, la API y las integraciones.
    Se inicializa en main.py antes de arrancar cualquier componente.
    """

    def __init__(self):
        self.pool            = None   # DBPool
        self.llamadas        = None   # LlamadasDB
        self.grupos          = None   # GruposDB
        self.usuarios        = None   # UsuariosDB
        self.afiliacion      = None   # AfiliacionConfig
        self.keyword_filter  = None   # KeywordFilter
        self.bot             = None   # TelegramBot
        self.email           = None   # EmailNotifier
        self.radio_connected  = False
        self.streaming_active = False


app_state = AppState()
