import serial
import time

class MotorolaPEI:

    def __init__(self, port: str, baud: int = 9600):
        self.ser = serial.Serial(port, baudrate=baud, timeout=1)
        time.sleep(1)
        self.current_gssi = None
        self.last_switch = 0
        self.send("AT")
        self.send("ATE0")

    def send(self, cmd: str) -> str:
        self.ser.write((cmd + "\r").encode())
        resp = self.ser.readline().decode(errors="ignore").strip()
        return resp

    def set_active_gssi(self, gssi: str):
        now = time.time()
        if gssi == self.current_gssi:
            return
        if now - self.last_switch < 2:
            return
        cmd = f"AT+CTGS={gssi}"
        print(f"[PEI] Cambiando GSSI -> {gssi}")
        resp = self.send(cmd)
        print(f"[PEI] Radio respondió: {resp}")
        self.current_gssi = gssi
        self.last_switch = now

    def set_scan_list(self, scan_list: str):
        cmd = f"AT+CGSSI={scan_list}"
        print(f"[PEI] Cambiando Scan List -> {scan_list}")
        resp = self.send(cmd)
        print(f"[PEI] Radio respondió: {resp}")