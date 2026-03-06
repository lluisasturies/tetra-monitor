import os
import serial
import threading
import time
import glob
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)
call_logger = logging.getLogger("calls")

class PEIDaemon:
    def __init__(self, motorola_pei, audio_buffer, stt_processor, keyword_filter, db, bot, port: Optional[str] = None, baudrate: int = 115200):
        self.radio = motorola_pei
        self.audio_buffer = audio_buffer
        self.stt = stt_processor
        self.kf = keyword_filter
        self.db = db
        self.bot = bot
        self.port = port
        self.baudrate = baudrate
        self.running = False

    def detectar_puerto_pei(self):
        if self.port and os.path.exists(self.port):
            logger.info(f"Usando puerto especificado: {self.port}")
            return self.port

        posibles_puertos = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        if posibles_puertos:
            puerto = posibles_puertos[0]
            logger.warning(f"Puerto configurado no encontrado. Detectado automáticamente: {puerto}")
            return puerto

        logger.critical("No se detectó ningún dispositivo Motorola PEI conectado")
        return None

    def procesar_llamada(self, grupo, ssi, streamer=None):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"evento_{grupo}_{ssi}_{timestamp}.flac"

        call_logger.info(f"CALL START | GSSI:{grupo} | SSI:{ssi}")
        self.audio_buffer.start_recording()
        logger.info(f"Grabando llamada Grupo:{grupo} SSI:{ssi}")

        while self.audio_buffer.recording and self.running:
            time.sleep(0.5)
            if streamer:
                audio_chunk = self.audio_buffer.get_chunk()
                if audio_chunk is not None:
                    streamer.send_audio(audio_chunk)

        path_audio = self.audio_buffer.stop_recording(filename)
        logger.info(f"Audio guardado {path_audio}")

        try:
            texto = self.stt.transcribir(path_audio)
            logger.info(f"Transcripción: {texto}")
        except Exception:
            logger.exception("Error en STT")
            texto = ""

        if self.kf.contiene_evento(texto):
            self.db.guardar_evento(grupo, ssi, texto, path_audio)
            self.bot.enviar_alerta(grupo, ssi, texto)
            call_logger.info(f"EVENT DETECTED | GSSI:{grupo} | SSI:{ssi} | TEXT:{texto}")
            logger.info("Evento relevante detectado y notificado")
        else:
            logger.info("No se detectaron palabras clave")

        call_logger.info(f"CALL END | GSSI:{grupo} | SSI:{ssi} | AUDIO:{path_audio}")

    def escuchar_pei(self, streamer=None):
        port_detected = self.detectar_puerto_pei()
        if port_detected is None:
            logger.critical("Finalizando daemon por falta de dispositivo PEI")
            return

        try:
            ser = serial.Serial(port_detected, self.baudrate, timeout=1)
            logger.info(f"Conectado a PEI en {port_detected} a {self.baudrate} bps")
        except serial.SerialException:
            logger.exception("No se pudo conectar al dispositivo PEI")
            return

        self.audio_buffer.start_buffer()
        logger.info("Audio buffer iniciado")
        self.running = True

        try:
            while self.running:
                frame = ser.readline()
                if not frame:
                    continue
                line = frame.decode(errors="ignore").strip()
                if line.startswith("CALL_START"):
                    _, grupo_str, ssi_str = line.split(";")
                    grupo = int(grupo_str)
                    ssi = int(ssi_str)
                    logger.debug(f"CALL_START detectado GSSI:{grupo} SSI:{ssi}")
                    threading.Thread(target=self.procesar_llamada, args=(grupo, ssi, streamer), daemon=True).start()
                elif line.startswith("CALL_END"):
                    logger.debug("CALL_END detectado")
                    self.audio_buffer.recording = False
        except KeyboardInterrupt:
            logger.info("Interrupción recibida, cerrando PEI daemon...")
        finally:
            self.shutdown(streamer)

    def shutdown(self, streamer=None):
        logger.info("Deteniendo PEI daemon y audio buffer")
        self.running = False
        self.audio_buffer.stop_buffer()
        if streamer:
            logger.info("Deteniendo streaming")
            streamer.stop()