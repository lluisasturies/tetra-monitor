class KeywordFilter:
    def __init__(self, keywords):
        self.keywords = [k.lower() for k in keywords]

    def contiene_evento(self, texto):
        texto = texto.lower()
        return any(k in texto for k in self.keywords)