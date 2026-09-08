from enum import Enum


class Comando(Enum):
    """O que a usuária pediu.

    `DESCONHECIDO` não é erro: qualquer entrada da conversa autorizada que não
    seja um comando conhecido recebe a ajuda curta.
    """

    START = "/start"
    FRASE = "/frase"
    STATUS = "/status"
    DESCONHECIDO = "desconhecido"

    @classmethod
    def de_texto(cls, texto: str | None) -> "Comando":
        if not texto:
            return cls.DESCONHECIDO
        # "/frase@nome_do_bot" e "/frase argumento" valem como "/frase".
        primeira = texto.strip().split()[0] if texto.strip() else ""
        primeira = primeira.split("@")[0].lower()
        for comando in (cls.START, cls.FRASE, cls.STATUS):
            if primeira == comando.value:
                return comando
        return cls.DESCONHECIDO
