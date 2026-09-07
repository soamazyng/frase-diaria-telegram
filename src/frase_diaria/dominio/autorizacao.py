import hmac
from dataclasses import dataclass
from enum import Enum


class Recusa(Enum):
    """Motivo pelo qual uma entrada não é aceita.

    O motivo serve ao diagnóstico interno; a fronteira HTTP não o revela ao
    chamador, para não transformar a resposta em um oráculo da configuração.
    """

    SEGREDO_INVALIDO = "segredo_invalido"
    CONVERSA_NAO_PRIVADA = "conversa_nao_privada"
    CHAT_NAO_AUTORIZADO = "chat_nao_autorizado"


@dataclass(frozen=True)
class Conversa:
    chat_id: int
    tipo: str


@dataclass(frozen=True)
class PoliticaDeAcesso:
    """Quem pode falar com o bot.

    O bot é de usuária única: uma conversa privada, um chat_id.
    """

    segredo_esperado: str
    chat_id_autorizado: int

    def avaliar(self, segredo: str | None, conversa: Conversa) -> Recusa | None:
        """Devolve o motivo da recusa, ou None quando a entrada é aceita.

        A ordem é deliberada: o segredo primeiro, para que quem não o tenha não
        consiga descobrir qual conversa é a autorizada comparando respostas.
        """
        if segredo is None or not hmac.compare_digest(segredo, self.segredo_esperado):
            return Recusa.SEGREDO_INVALIDO
        if conversa.tipo != "private":
            return Recusa.CONVERSA_NAO_PRIVADA
        if conversa.chat_id != self.chat_id_autorizado:
            return Recusa.CHAT_NAO_AUTORIZADO
        return None
