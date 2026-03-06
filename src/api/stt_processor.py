import whisper

class STTProcessor:
    def __init__(self, model_name="base", language="es"):
        self.model = whisper.load_model(model_name)
        self.language = language

    def transcribir(self, filepath):
        result = self.model.transcribe(filepath, language=self.language)
        texto = result.get("text", "").lower()
        return texto