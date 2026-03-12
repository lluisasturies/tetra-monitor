from .icecast_streamer import IcecastStreamer
from .rtmp_streamer import RTMPStreamer
from .zello_streamer import ZelloStreamer


def create_streamer(config: dict):
    """
    Crea el streamer segun la configuracion.

    Los streamers son mutuamente excluyentes: solo se activa uno a la vez.
    Si se definen varias URLs se aplica esta prioridad y se avisa por log:
      1. zello_url   — PTT-aware, credenciales sensibles en .env
      2. rtmp_url    — streaming continuo via RTMP
      3. icecast_url — streaming continuo via Icecast

    Para activar un streamer basta con definir su URL en config.yaml.
    Las credenciales de Zello van en .env:
      ZELLO_USERNAME, ZELLO_PASSWORD, ZELLO_TOKEN
    """
    import os
    from core.logger import logger

    samplerate = config.get("samplerate", 16000)
    channels   = config.get("channels", 1)
    bitrate    = config.get("bitrate", "128k")

    zello_url   = config.get("zello_url",   "").strip()
    rtmp_url    = config.get("rtmp_url",    "").strip()
    icecast_url = config.get("icecast_url", "").strip()

    # Advertir si el usuario ha definido mas de una URL: solo la prioritaria
    # se activara; las demas se ignoraran en silencio sin este aviso.
    activas = [u for u in [zello_url, rtmp_url, icecast_url] if u]
    if len(activas) > 1:
        logger.warning(
            f"[Streaming] Se han definido {len(activas)} streamers a la vez "
            f"(zello_url, rtmp_url, icecast_url). Solo se activara el de mayor "
            f"prioridad. Deja activa unicamente la URL que quieras usar."
        )

    if zello_url:
        username = os.getenv("ZELLO_USERNAME", "")
        password = os.getenv("ZELLO_PASSWORD", "")
        token    = os.getenv("ZELLO_TOKEN", "")
        if not all([username, password, token]):
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

    if rtmp_url:
        return RTMPStreamer(rtmp_url, samplerate=samplerate, channels=channels, bitrate=bitrate)

    if icecast_url:
        return IcecastStreamer(icecast_url, samplerate=samplerate, channels=channels, bitrate=bitrate)

    return None
