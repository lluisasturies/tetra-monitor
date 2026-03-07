from streaming.base_streamer import BaseStreamer


class RTMPStreamer(BaseStreamer):
    def build_ffmpeg_cmd(self) -> list:
        return [
            "ffmpeg",
            "-f", "f32le",
            "-ar", str(self.samplerate),
            "-ac", str(self.channels),
            "-i", "-",
            "-c:a", "aac",
            "-f", "flv",
            self.url
        ]
