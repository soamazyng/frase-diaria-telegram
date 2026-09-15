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

    O bot é privado a um conjunto pequeno e fixo de destinatários: cada um é uma
    conversa privada, identificada pelo próprio chat_id (spec v2,
    `.scratch/v2-telegram-bot.md`).
    """

    segredo_esperado: str
    chat_ids_autorizados: frozenset[int]

    def conferir_segredo(self, segredo: str | None) -> Recusa | None:
        """Confere apenas o cabeçalho, sem olhar o corpo da requisição.

        Existe separado para poder ser chamado **antes** de interpretar o corpo:
        a spec (4.7) fala em reconhecer "atualizações irrelevantes já validadas",
        e decidir que algo é irrelevante antes de conferir o segredo daria a
        qualquer origem uma resposta 200 e uma linha de log.
        """
        if segredo is None or not hmac.compare_digest(segredo, self.segredo_esperado):
            return Recusa.SEGREDO_INVALIDO
        return None

    def conferir_conversa(self, conversa: Conversa) -> Recusa | None:
        """Confere origem e pertencimento ao conjunto de destinatários autorizados.

        Só faz sentido após o segredo passar.
        """
        if conversa.tipo != "private":
            return Recusa.CONVERSA_NAO_PRIVADA
        if conversa.chat_id not in self.chat_ids_autorizados:
            return Recusa.CHAT_NAO_AUTORIZADO
        return None

    def avaliar(self, segredo: str | None, conversa: Conversa) -> Recusa | None:
        """As duas conferências em ordem: segredo primeiro, sempre.

        Quem não tem o segredo não pode descobrir qual conversa é a autorizada
        comparando respostas.
        """
        return self.conferir_segredo(segredo) or self.conferir_conversa(conversa)
