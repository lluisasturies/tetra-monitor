import serial
import time
from core.logger import logger


class MotorolaPEI:
    def __init__(self, port: str, baud: int = 9600):
        try:
            self.ser = serial.Serial(port, baudrate=baud, timeout=1)
            time.sleep(1)
            self.current_gssi = None
            self.last_switch = 0
            logger.info(f"Inicializando MotorolaPEI en puerto {port} con baud {baud}")
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
        cmd = f"AT+CGSSI={scan_list}"
        logger.info(f"[PEI] Cambiando Scan List -> {scan_list}")
        resp = self.send(cmd)
        logger.info(f"[PEI] Radio respondió: {resp}")

    def read_event(self):
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

    def _parse_event(self, line: str):
        """Parsea una línea PEI y devuelve un objeto evento o None."""
        # Ejemplo de tramas esperadas (ajustar según protocolo real del MTM5400):
        # PTT_START: "+CTSDSR: 1,<grupo>,<ssi>"
        # PTT_END:   "+CTSDSR: 0,<grupo>,<ssi>"
        if "+CTSDSR:" in line:
            try:
                parts = line.split(":")[1].strip().split(",")
                estado = parts[0].strip()
                grupo = int(parts[1].strip())
                ssi = int(parts[2].strip())

                class Event:
                    pass

                ev = Event()
                ev.grupo = grupo
                ev.ssi = ssi
                ev.type = "PTT_START" if estado == "1" else "PTT_END"
                return ev
            except (IndexError, ValueError) as e:
                logger.warning(f"[PEI] No se pudo parsear trama: '{line}' — {e}")
                return None
        return None

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.info("[PEI] Puerto serie cerrado")
