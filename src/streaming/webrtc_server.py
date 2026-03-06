import os
import asyncio
import logging
import yaml
import numpy as np
import sounddevice as sd
import av

from aiohttp import web
from aiortc import RTCPeerConnection, MediaStreamTrack, RTCSessionDescription

# -------------------------
# Configuración desde YAML
# -------------------------
base_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_dir, "../../config/config.yaml")

try:
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)
except FileNotFoundError:
    raise FileNotFoundError(f"No se encontró el archivo de configuración: {config_path}")

webrtc_cfg = cfg.get("webrtc", {})

PORT = webrtc_cfg.get("port", 8080)
HOST = webrtc_cfg.get("host", "0.0.0.0")
SAMPLERATE = webrtc_cfg.get("samplerate", 16000)
CHANNELS = webrtc_cfg.get("channels", 1)
CHUNK = webrtc_cfg.get("chunk_size", 1024)

# -------------------------
# Logging
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)

# -------------------------
# Audio Track
# -------------------------
class AudioTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.queue = asyncio.Queue()

        # Callback para captura del micrófono
        def callback(indata, frames, time, status):
            if status:
                logging.warning(f"SoundDevice status: {status}")
            self.queue.put_nowait(indata.copy())

        # Iniciar stream
        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLERATE,
                channels=CHANNELS,
                blocksize=CHUNK,
                callback=callback
            )
            self.stream.start()
            logging.info("Stream de audio iniciado correctamente")
        except Exception as e:
            logging.error(f"No se pudo iniciar el stream de audio: {e}")
            raise

    async def recv(self):
        frame = await self.queue.get()
        audio_frame = av.AudioFrame.from_ndarray(frame, format="flt", layout="mono")
        audio_frame.sample_rate = SAMPLERATE
        return audio_frame

# -------------------------
# Servidor WebRTC
# -------------------------
pcs = set()

async def offer(request):
    try:
        params = await request.json()
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
        pc = RTCPeerConnection()
        pcs.add(pc)
        pc.addTrack(AudioTrack())

        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        logging.info("Nueva conexión WebRTC establecida")
        return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})
    except Exception as e:
        logging.error(f"Error al procesar offer: {e}")
        return web.Response(status=500, text=str(e))

app = web.Application()
app.router.add_post("/offer", offer)

if __name__ == "__main__":
    logging.info(f"Iniciando WebRTC server en {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT)