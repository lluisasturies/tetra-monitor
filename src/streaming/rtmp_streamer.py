from streaming.base_streamer import BaseStreamer


class RTMPStreamer(BaseStreamer):
    def build_ffmpeg_cmd(self) -> list:
        return [
            "ffmpeg",
            "-f", "f32le",               # formato de entrada: float 32-bit little endian
            "-ar", str(self.samplerate), # sample rate
            "-ac", str(self.channels),   # canales (1 = mono)
            "-i", "-",                   # input desde stdin
            "-c:a", "aac",               # codec AAC (requerido por RTMP)
            "-b:a", self.bitrate,        # bitrate
            "-f", "flv",                 # contenedor FLV (requerido por RTMP)
            self.url
        ]
