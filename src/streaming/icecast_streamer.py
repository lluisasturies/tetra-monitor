from streaming.base_streamer import BaseStreamer


class IcecastStreamer(BaseStreamer):
    def build_ffmpeg_cmd(self) -> list:
        return [
            "ffmpeg",
            "-f", "f32le",               # formato de entrada: float 32-bit little endian
            "-ar", str(self.samplerate), # sample rate
            "-ac", str(self.channels),   # canales (1 = mono)
            "-i", "-",                   # input desde stdin
            "-c:a", "libmp3lame",        # codec MP3
            "-b:a", self.bitrate,        # bitrate
            "-f", "mp3",                 # contenedor MP3
            self.url
        ]
