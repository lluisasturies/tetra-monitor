```
░▀█▀░█▀▀░▀█▀░█▀▄░█▀█░█▄█░█▀█░█▀█░▀█▀░▀█▀░█▀█░█▀▄
░░█░░█▀▀░░█░░█▀▄░█▀█░█░█░█░█░█░█░░█░░░█░░█░█░█▀▄
░░▀░░▀▀▀░░▀░░▀░▀░▀░▀░▀░▀░▀▀▀░▀░▀░▀▀▀░░▀░░▀▀▀░▀░▀
```

# 🌐 TETRA Monitor
Proyecto para **monitorización de redes TETRA** usando:

- 📡 **Motorola MTM5400**  
- 🖥️ **Raspberry Pi 5**  
- 🗄️ **PostgreSQL** para almacenamiento  
- 🗣️ **Whisper / Vosk** para Speech-to-Text  
- 📲 **Notificaciones por Telegram**  
- 🔗 **API REST** para consultar eventos  
- 🎧 **Streaming de audio WebRTC** para escuchar remotamente  

---

## 🗂️ Estructura del proyecto
+ tetra-monitor/
  + src/
    + streaming/
  + config/
  + scripts/
  + data/
  + logs/

## Instalación
```bash
chmod +x scripts/setup.sh
scripts/setup.sh
```

## ▶️ Iniciar TETRA Monitor
```bash
chmod +x scripts/start.sh
scripts/start.sh
```

## 🎧 Escuchar audio remotamente (WebRTC)
```bash
source ~/tetra-monitor/venv/bin/activate
python3 src/streaming/webrtc_server.py
```

## 📝 Notas importantes
- 📂 Logs y grabaciones se guardan en logs/ y data/audio/.
- ⚙️ Personaliza palabras clave y configuraciones en config/.
- 🔒 Para producción remota: usar HTTPS/WSS y autenticación en WebRTC.