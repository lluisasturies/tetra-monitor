from .icecast_streamer import IcecastStreamer
from .rtmp_streamer import RTMPStreamer
from .zello_streamer import ZelloStreamer


def create_streamer(config: dict):
    """
    Crea el streamer segun la configuracion.

    Prioridad:
      1. zello_url   — PTT-aware, credenciales sensibles en .env
      2. rtmp_url    — streaming continuo via RTMP
      3. icecast_url — streaming continuo via Icecast

    La URL activa el streamer (igual que rtmp_url / icecast_url).
    Las credenciales de Zello van en .env para no exponerlas en el YAML:
      ZELLO_USERNAME, ZELLO_PASSWORD, ZELLO_TOKEN

    Solo se activa un streamer a la vez.
    """
    import os

    samplerate = config.get("samplerate", 16000)
    channels   = config.get("channels", 1)
    bitrate    = config.get("bitrate", "128k")

    zello_url = config.get("zello_url", "").strip()
    if zello_url:
        username = os.getenv("ZELLO_USERNAME", "")
        password = os.getenv("ZELLO_PASSWORD", "")
        token    = os.getenv("ZELLO_TOKEN", "")
        if not all([username, password, token]):
            from core.logger import logger
            logger.error(
                "[Zello] Faltan credenciales en .env. "
                "Define ZELLO_USERNAME, ZELLO_PASSWORD y ZELLO_TOKEN."
            )
            return None
        return ZelloStreamer(
            username=username,
            password=password,
            token=token,
            channel=zello_url,
            samplerate=samplerate,
            channels=channels,
        )

    rtmp_url    = config.get("rtmp_url", "").strip()
    icecast_url = config.get("icecast_url", "").strip()

    if rtmp_url:
        return RTMPStreamer(rtmp_url, samplerate=samplerate, channels=channels, bitrate=bitrate)
    elif icecast_url:
        return IcecastStreamer(icecast_url, samplerate=samplerate, channels=channels, bitrate=bitrate)

    return None
