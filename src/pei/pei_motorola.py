import serial
import time
from core import logger

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
            logger.debug(f"[PEI] Cambio de GSSI ignorado por tiempo mínimo entre cambios")
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