from streaming.base_streamer import BaseStreamer

class RTMPStreamer(BaseStreamer):
    def __init__(self, url: str, samplerate: int = 48000, channels: int = 1, bitrate: str = "128k"):
        super().__init__(url, samplerate, channels)
        self.bitrate = bitrate

    def build_ffmpeg_cmd(self) -> list:
        return [
            "ffmpeg",
            "-f", "f32le",                  # formato de entrada: float 32-bit little endian
            "-ar", str(self.samplerate),    # sample rate
            "-ac", str(self.channels),      # canales (1 = mono)
            "-i", "-",                      # input desde stdin
            "-c:a", "aac",                  # codec de audio AAC (requerido por RTMP)
            "-b:a", self.bitrate,           # bitrate
            "-f", "flv",                    # contenedor FLV (requerido por RTMP)
            self.url                        # destino rtmp://...
        ]