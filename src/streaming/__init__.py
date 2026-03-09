from .icecast_streamer import IcecastStreamer
from .rtmp_streamer import RTMPStreamer


def create_streamer(config: dict):
    rtmp_url    = config.get("rtmp_url")
    icecast_url = config.get("icecast_url")
    samplerate  = config.get("samplerate", 16000)
    channels    = config.get("channels", 1)
    bitrate     = config.get("bitrate", "128k")

    if rtmp_url:
        return RTMPStreamer(rtmp_url.strip(), samplerate=samplerate, channels=channels, bitrate=bitrate)
    elif icecast_url:
        return IcecastStreamer(icecast_url.strip(), samplerate=samplerate, channels=channels, bitrate=bitrate)
    else:
        return None
