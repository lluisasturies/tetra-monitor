class AppState:
    """
    Estado global compartido entre el daemon PEI, la API y los integraciones.
    Se inicializa en main.py antes de arrancar cualquier componente.
    """

    def __init__(self):
        self.pool            = None   # DBPool
        self.llamadas        = None   # LlamadasDB
        self.grupos          = None   # GruposDB
        self.usuarios        = None   # UsuariosDB  <-- nuevo
        self.afiliacion      = None   # AfiliacionConfig
        self.keyword_filter  = None   # KeywordFilter
        self.bot             = None   # TelegramBot
        self.email           = None   # EmailNotifier
        self.radio_connected = False
        self.streaming_active = False

        # Refresh tokens en memoria (legado -- ya no se usan si BD disponible)
        # Se mantiene por compatibilidad con tests que no montan BD.
        self.refresh_tokens: set = set()


app_state = AppState()
