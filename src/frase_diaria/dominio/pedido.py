from dataclasses import dataclass, replace
from enum import Enum


class Origem(Enum):
    DIARIA = "diaria"
    EXTRA = "extra"


class EstadoDoPedido(Enum):
    """Estados que o tracer bullet exercita.

    O ticket 07 acrescenta RESERVADO, AGUARDANDO_TENTATIVA, INCERTO e EXPIRADO.
    Os nomes aqui são os definitivos, para que o 07 estenda em vez de renomear.
    """

    PENDENTE = "pendente"
    ENVIANDO = "enviando"
    ENVIADO = "enviado"
    PARCIAL = "parcial"
    FALHOU = "falhou"

    @property
    def terminal(self) -> bool:
        return self in (EstadoDoPedido.ENVIADO, EstadoDoPedido.PARCIAL, EstadoDoPedido.FALHOU)


@dataclass(frozen=True)
class Pedido:
    """Uma solicitação de envio, com identidade que sobrevive a reinícios."""

    identidade: str
    origem: Origem
    chat_id: int
    estado: EstadoDoPedido = EstadoDoPedido.PENDENTE
    frase_reservada: str | None = None

    @staticmethod
    def identidade_de_extra(update_id: int) -> str:
        """Identidade de um extra: o bot mais o update_id do Telegram (spec, 4.6)."""
        return f"extra#{update_id}"

    def _recusar_se_terminal(self) -> None:
        if self.estado.terminal:
            raise ValueError(f"pedido em estado terminal ({self.estado.value}) não muda")

    def reservar(self, frase: str) -> "Pedido":
        self._recusar_se_terminal()
        return replace(self, frase_reservada=frase, estado=EstadoDoPedido.ENVIANDO)

    def concluir(self) -> "Pedido":
        self._recusar_se_terminal()
        if self.frase_reservada is None:
            raise ValueError("não é possível concluir pedido sem frase reservada")
        return replace(self, estado=EstadoDoPedido.ENVIADO)

    def falhar(self, alguma_parte_enviada: bool) -> "Pedido":
        """Encerra o pedido sem sucesso.

        Falha comprovada sem nenhum envio libera a reserva. Entrega parcial mantém
        a frase consumida, para não reiniciar automaticamente algo que já pode ter
        chegado à usuária (spec, 4.4).
        """
        self._recusar_se_terminal()
        if alguma_parte_enviada:
            return replace(self, estado=EstadoDoPedido.PARCIAL)
        return replace(self, estado=EstadoDoPedido.FALHOU, frase_reservada=None)
