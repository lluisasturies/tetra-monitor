import asyncio
import threading
import json
import struct
import time
from core.logger import logger

try:
    import websockets
    import opuslib
    import numpy as np
    _ZELLO_DEPS_AVAILABLE = True
except ImportError:
    _ZELLO_DEPS_AVAILABLE = False


ZELLO_WSS_URL = "wss://zello.io/ws"

# Parametros Opus requeridos por Zello
OPUS_SAMPLE_RATE  = 16000
OPUS_CHANNELS     = 1
OPUS_FRAME_MS     = 60      # Zello requiere frames de 60ms
OPUS_FRAME_SIZE   = int(OPUS_SAMPLE_RATE * OPUS_FRAME_MS / 1000)  # 960 muestras
OPUS_BITRATE      = 16000


class ZelloStreamer:
    """
    Streamer para Zello via WebSocket.

    A diferencia de RTMP/Icecast (audio continuo), Zello es PTT:
    - send_text_message(text) -> envia un mensaje de texto al canal
    - call_start()            -> abre un stream de voz en el canal
    - send_audio(audio)       -> envia chunks de audio codificados en Opus
    - call_end()              -> cierra el stream

    Flujo tipico con TETRA:
      CALL_START -> send_text_message('[TETRA] Grupo: ... | SSI: ...')
      PTT_START  -> call_start()
      <audio>    -> send_audio(chunk)
      PTT_END    -> call_end()

    Configuracion en config.yaml:
      streaming:
        zello_url: "nombre-del-canal"   # activa Zello (analogo a rtmp_url/icecast_url)

    Credenciales sensibles en .env (no en el YAML):
      ZELLO_USERNAME, ZELLO_PASSWORD, ZELLO_TOKEN

    Requiere credenciales de desarrollador Zello:
    https://github.com/zelloptt/zello-channel-api
    """

    def __init__(self, username: str, password: str, token: str, channel: str,
                 samplerate: int = 16000, channels: int = 1, **kwargs):
        if not _ZELLO_DEPS_AVAILABLE:
            raise RuntimeError(
                "Dependencias de Zello no instaladas. "
                "Ejecuta: pip install websockets opuslib"
            )

        self.username   = username
        self.password   = password
        self.token      = token
        self.channel    = channel
        self.samplerate = samplerate
        self.channels   = channels

        self.running    = False
        self._ws        = None
        self._stream_id = None
        self._packet_id = 0
        self._in_call   = False
        self._loop      = asyncio.new_event_loop()
        self._encoder   = opuslib.Encoder(OPUS_SAMPLE_RATE, OPUS_CHANNELS, opuslib.APPLICATION_VOIP)
        self._encoder.bitrate = OPUS_BITRATE
        self._buf       = b""

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"[Zello] Streamer iniciado -> canal '{self.channel}'")

    # ------------------------------------------------------------------
    # Hilo asyncio
    # ------------------------------------------------------------------

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_loop())

    async def _connect_loop(self):
        """Reconecta automaticamente si se cae la conexion WebSocket."""
        while True:
            try:
                async with websockets.connect(ZELLO_WSS_URL) as ws:
                    self._ws = ws
                    self.running = True
                    logger.info("[Zello] WebSocket conectado")
                    await self._authenticate()
                    await self._listen()
            except Exception as e:
                logger.error(f"[Zello] Error de conexion: {e}. Reintentando en 10s...")
                self.running = False
                self._ws = None
                await asyncio.sleep(10)

    async def _authenticate(self):
        auth = {
            "command": "logon",
            "seq": 1,
            "auth_token": self.token,
            "username": self.username,
            "password": self.password,
            "channel": self.channel,
        }
        await self._ws.send(json.dumps(auth))
        resp = json.loads(await self._ws.recv())
        if not resp.get("success"):
            raise RuntimeError(f"[Zello] Autenticacion fallida: {resp}")
        logger.info(f"[Zello] Autenticado en canal '{self.channel}'")

    async def _listen(self):
        """Recibe mensajes del servidor. Los mensajes binarios son audio entrante (ignorado)."""
        async for message in self._ws:
            if isinstance(message, str):
                data = json.loads(message)
                if data.get("command") == "on_stream_start":
                    logger.debug(f"[Zello] Stream entrante: {data}")

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def send_text_message(self, text: str):
        if not self.running:
            logger.debug("[Zello] send_text_message ignorado: sin conexion")
            return
        asyncio.run_coroutine_threadsafe(self._send_text(text), self._loop)
        logger.debug(f"[Zello] Mensaje de texto encolado: {text}")

    def call_start(self):
        """Abre un stream PTT en Zello. Llamar cuando llega PTT_START de TETRA."""
        if not self.running or self._in_call:
            return
        self._packet_id = 0
        self._buf = b""
        future = asyncio.run_coroutine_threadsafe(self._start_stream(), self._loop)
        try:
            self._stream_id = future.result(timeout=5)
            self._in_call = True
            logger.info(f"[Zello] Stream abierto (id={self._stream_id})")
        except Exception as e:
            logger.error(f"[Zello] No se pudo abrir stream: {e}")

    def call_end(self):
        """Cierra el stream PTT. Llamar cuando llega PTT_END de TETRA."""
        if not self._in_call:
            return
        if self._buf:
            self._flush_buffer()
        future = asyncio.run_coroutine_threadsafe(self._stop_stream(), self._loop)
        try:
            future.result(timeout=5)
        except Exception as e:
            logger.error(f"[Zello] Error cerrando stream: {e}")
        self._in_call = False
        self._stream_id = None
        logger.info("[Zello] Stream cerrado")

    def send_audio(self, audio):
        if not self._in_call or not self.running:
            return
        # numpy se importa a nivel de modulo junto al resto de dependencias opcionales
        pcm16 = (audio * 32767).clip(-32768, 32767).astype(np.int16).tobytes()
        self._buf += pcm16
        self._flush_buffer()

    def _flush_buffer(self):
        frame_bytes = OPUS_FRAME_SIZE * 2
        while len(self._buf) >= frame_bytes:
            frame = self._buf[:frame_bytes]
            self._buf = self._buf[frame_bytes:]
            encoded = self._encoder.encode(frame, OPUS_FRAME_SIZE)
            asyncio.run_coroutine_threadsafe(
                self._send_audio_packet(encoded), self._loop
            )

    # ------------------------------------------------------------------
    # Corrutinas internas
    # ------------------------------------------------------------------

    async def _send_text(self, text: str):
        if not self._ws:
            return
        try:
            cmd = {"command": "send_text_message", "seq": int(time.time()), "text": text}
            await self._ws.send(json.dumps(cmd))
        except Exception as e:
            logger.error(f"[Zello] Error enviando mensaje de texto: {e}")

    async def _start_stream(self) -> int:
        cmd = {
            "command": "start_stream",
            "seq": 2,
            "type": "audio",
            "codec": "opus",
            "codec_header": self._build_codec_header(),
            "transaction_id": int(time.time()),
        }
        await self._ws.send(json.dumps(cmd))
        resp = json.loads(await self._ws.recv())
        if "stream_id" not in resp:
            raise RuntimeError(f"start_stream fallo: {resp}")
        return resp["stream_id"]

    async def _stop_stream(self):
        if self._stream_id is None:
            return
        await self._ws.send(json.dumps({"command": "stop_stream", "stream_id": self._stream_id}))

    async def _send_audio_packet(self, opus_data: bytes):
        if self._stream_id is None or not self.running:
            return
        header = struct.pack(">BII", 0x01, self._stream_id, self._packet_id)
        self._packet_id += 1
        try:
            await self._ws.send(header + opus_data)
        except Exception as e:
            logger.error(f"[Zello] Error enviando paquete de audio: {e}")

    def _build_codec_header(self) -> str:
        import base64
        header = struct.pack(">HBB", OPUS_SAMPLE_RATE, 1, OPUS_FRAME_MS)
        return base64.b64encode(header).decode()

    def stop(self):
        if self._in_call:
            self.call_end()
        self.running = False
        self._loop.call_soon_threadsafe(self._loop.stop)
        logger.info("[Zello] Streamer detenido")
