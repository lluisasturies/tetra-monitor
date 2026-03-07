from .icecast_streamer import IcecastStreamer
from .rtmp_streamer import RTMPStreamer

def create_streamer(config: dict):
    rtmp_url = config.get("rtmp_url")
    icecast_url = config.get("icecast_url")

    if rtmp_url:
        return RTMPStreamer(rtmp_url.strip())

    elif icecast_url:
        return IcecastStreamer(icecast_url.strip())

    else:
        return None