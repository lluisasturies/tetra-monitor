import re
import serial
import time
from core.logger import logger
from pei.models.pei_event import PEIEvent

# Patrones permitidos para comandos AT
_RE_GSSI      = re.compile(r'^\d{1,8}$')           # solo dígitos, máx 8
_RE_SCAN_LIST = re.compile(r'^[\w\-]{1,32}$')       # alfanumérico y guión, máx 32


class MotorolaPEI:
    def __init__(self, port: str, baud: int = 9600):
        try:
            logger.info(f"Inicializando MotorolaPEI en puerto {port} con baud {baud}")
            self.ser = serial.Serial(port, baudrate=baud, timeout=1)
            time.sleep(1)
            self.current_gssi = None
            self.last_switch = 0
            self.send("AT")
            self.send("ATE0")
        except serial.SerialException as e:
            logger.critical(f"No se pudo abrir el puerto {port}: {e}")
            raise

    def send(self, cmd: str) -> str:
        try:
            self.ser.write((cmd + "\r").encode())
            resp = self.ser.readline().decode(errors="ignore").strip()
            logger.debug(f"[PEI] Comando enviado: {cmd} | Respuesta: {resp}")
            return resp
        except Exception as e:
            logger.error(f"[PEI] Error enviando comando '{cmd}': {e}")
            return ""

    def set_active_gssi(self, gssi: str):
        if not _RE_GSSI.match(gssi):
            logger.error(f"[PEI] GSSI rechazado por formato inválido: '{gssi}'")
            return
        now = time.time()
        if gssi == self.current_gssi:
            logger.debug(f"[PEI] GSSI {gssi} ya activo, sin cambios")
            return
        if now - self.last_switch < 2:
            logger.debug("[PEI] Cambio de GSSI ignorado por tiempo mínimo entre cambios")
            return
        cmd = f"AT+CTGS={gssi}"
        logger.info(f"[PEI] Cambiando GSSI -> {gssi}")
        resp = self.send(cmd)
        logger.info(f"[PEI] Radio respondió: {resp}")
        self.current_gssi = gssi
        self.last_switch = now

    def set_scan_list(self, scan_list: str):
        if not _RE_SCAN_LIST.match(scan_list):
            logger.error(f"[PEI] Scan list rechazada por formato inválido: '{scan_list}'")
            return
        # AT+CTSL: comando ETSI EN 300 392-5 para activar una scan list por nombre.
        # (Anteriormente se usaba AT+CGSSI por error, que es el comando de consulta de GSSI.)
        cmd = f"AT+CTSL={scan_list}"
        logger.info(f"[PEI] Cambiando Scan List -> {scan_list}")
        resp = self.send(cmd)
        logger.info(f"[PEI] Radio respondió: {resp}")

    def read_event(self) -> PEIEvent | None:
        """Lee una línea del puerto serie y la parsea como evento TETRA."""
        try:
            line = self.ser.readline().decode(errors="ignore").strip()
            if not line:
                return None
            logger.debug(f"[PEI] Línea recibida: {line}")
            return self._parse_event(line)
        except Exception as e:
            logger.error(f"[PEI] Error leyendo evento: {e}")
            return None

    def _parse_event(self, line: str) -> PEIEvent | None:
        # ---------------------------------------------------------------
        # +CTXG: <TxGrant>,<TxRqPrmsn>,<TxCont>,[<called_party_ssi>]
        # Transmission Grant — la red concede el turno de voz.
        # TxGrant=1: alguien ha empezado a hablar.
        # TxGrant=0: se deniega o libera el turno.
        # ---------------------------------------------------------------
        if "+CTXG:" in line:
            try:
                parts = line.split(":")[1].strip().split(",")
                tx_grant = int(parts[0].strip())
                return PEIEvent(type="PTT_START" if tx_grant == 1 else "PTT_END")
            except (IndexError, ValueError) as e:
                logger.warning(f"[PEI] No se pudo parsear +CTXG: '{line}' — {e}")
            return None

        # ---------------------------------------------------------------
        # +CDTXC: <cc_instance>
        # Down Transmission Ceased — el hablante actual dejó de transmitir.
        # ---------------------------------------------------------------
        if "+CDTXC:" in line:
            return PEIEvent(type="PTT_END")

        # ---------------------------------------------------------------
        # +CTICN: <cc_instance>,<call_status>,<AI_service>,
        #         <called_party_identity>,<called_party_identity_type>,
        #         [<called_party_ssi>],[<calling_party_ssi>],...
        # Incoming Call Notification — llamada entrante con GSSI y SSI.
        # ---------------------------------------------------------------
        if "+CTICN:" in line:
            try:
                parts = line.split(":")[1].strip().split(",")
                grupo = int(parts[3].strip()) if len(parts) > 3 else 0
                ssi   = int(parts[6].strip()) if len(parts) > 6 else 0
                return PEIEvent(type="CALL_START", grupo=grupo, ssi=ssi)
            except (IndexError, ValueError) as e:
                logger.warning(f"[PEI] No se pudo parsear +CTICN: '{line}' — {e}")
            return None

        # ---------------------------------------------------------------
        # +CTCC: <cc_instance>,<call_status>,...
        # Call Connect — llamada establecida.
        # ---------------------------------------------------------------
        if "+CTCC:" in line:
            return PEIEvent(type="CALL_CONNECTED")

        # ---------------------------------------------------------------
        # +CTCR: <cc_instance>,<disconnect_cause>
        # Call Release — llamada terminada.
        # ---------------------------------------------------------------
        if "+CTCR:" in line:
            return PEIEvent(type="CALL_END")

        # ---------------------------------------------------------------
        # +CTXD: <cc_instance>,<TxDemandPriority>
        # Transmit Demand — el propio radio ha pulsado PTT para transmitir.
        # ---------------------------------------------------------------
        if "+CTXD:" in line:
            return PEIEvent(type="TX_DEMAND")

        return None

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.info("[PEI] Puerto serie cerrado")
