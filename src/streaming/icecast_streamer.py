from streaming.base_streamer import BaseStreamer


class IcecastStreamer(BaseStreamer):
    def build_ffmpeg_cmd(self) -> list:
        return [
            "ffmpeg",
            "-f", "f32le",
            "-ar", str(self.samplerate),
            "-ac", str(self.channels),
            "-i", "-",
            "-c:a", "libmp3lame",
            "-f", "mp3",
            self.url
        ]
