from .icecast_streamer import IcecastStreamer
from .rtmp_streamer import RTMPStreamer
from .zello_streamer import ZelloStreamer


def create_streamer(config: dict):
    """
    Crea el streamer segun la configuracion.

    Prioridad:
      1. zello      — PTT-aware, requiere credenciales de desarrollador Zello
      2. rtmp_url   — streaming continuo via RTMP
      3. icecast_url — streaming continuo via Icecast

    Todas las opciones se configuran exclusivamente en config.yaml.
    Solo se activa un streamer a la vez.
    """
    samplerate = config.get("samplerate", 16000)
    channels   = config.get("channels", 1)
    bitrate    = config.get("bitrate", "128k")

    zello_cfg = config.get("zello", {})
    if zello_cfg.get("enabled", False):
        username = zello_cfg.get("username", "")
        password = zello_cfg.get("password", "")
        token    = zello_cfg.get("token", "")
        channel  = zello_cfg.get("channel", "")
        if not all([username, password, token, channel]):
            from core.logger import logger
            logger.error(
                "[Zello] Faltan credenciales en config.yaml. "
                "Define streaming.zello.username, password, token y channel."
            )
            return None
        return ZelloStreamer(
            username=username,
            password=password,
            token=token,
            channel=channel,
            samplerate=samplerate,
            channels=channels,
        )

    rtmp_url    = config.get("rtmp_url")
    icecast_url = config.get("icecast_url")

    if rtmp_url:
        return RTMPStreamer(rtmp_url.strip(), samplerate=samplerate, channels=channels, bitrate=bitrate)
    elif icecast_url:
        return IcecastStreamer(icecast_url.strip(), samplerate=samplerate, channels=channels, bitrate=bitrate)

    return None
