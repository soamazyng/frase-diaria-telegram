from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import Enum


class Origem(Enum):
    DIARIA = "diaria"
    EXTRA = "extra"


class EstadoDoPedido(Enum):
    """Estados persistentes de um pedido de envio."""

    PENDENTE = "pendente"
    RESERVADO = "reservado"
    ENVIANDO = "enviando"
    AGUARDANDO_TENTATIVA = "aguardando_tentativa"
    ENVIADO = "enviado"
    PARCIAL = "parcial"
    INCERTO = "incerto"
    FALHOU = "falhou"
    EXPIRADO = "expirado"

    @property
    def terminal(self) -> bool:
        return self in (
            EstadoDoPedido.ENVIADO,
            EstadoDoPedido.PARCIAL,
            EstadoDoPedido.INCERTO,
            EstadoDoPedido.FALHOU,
            EstadoDoPedido.EXPIRADO,
        )


_TRANSICOES_PERMITIDAS: dict[EstadoDoPedido, frozenset[EstadoDoPedido]] = {
    EstadoDoPedido.PENDENTE: frozenset(
        {
            EstadoDoPedido.RESERVADO,
            EstadoDoPedido.AGUARDANDO_TENTATIVA,
            EstadoDoPedido.FALHOU,
            EstadoDoPedido.EXPIRADO,
        }
    ),
    EstadoDoPedido.RESERVADO: frozenset(
        {
            EstadoDoPedido.ENVIANDO,
            EstadoDoPedido.AGUARDANDO_TENTATIVA,
            EstadoDoPedido.FALHOU,
            EstadoDoPedido.EXPIRADO,
        }
    ),
    EstadoDoPedido.ENVIANDO: frozenset(
        {
            EstadoDoPedido.AGUARDANDO_TENTATIVA,
            EstadoDoPedido.ENVIADO,
            EstadoDoPedido.PARCIAL,
            EstadoDoPedido.INCERTO,
            EstadoDoPedido.FALHOU,
            EstadoDoPedido.EXPIRADO,
        }
    ),
    EstadoDoPedido.AGUARDANDO_TENTATIVA: frozenset(
        {
            EstadoDoPedido.RESERVADO,
            EstadoDoPedido.ENVIANDO,
            EstadoDoPedido.AGUARDANDO_TENTATIVA,
            EstadoDoPedido.FALHOU,
            EstadoDoPedido.EXPIRADO,
        }
    ),
}


@dataclass(frozen=True)
class Pedido:
    """Uma solicitação de envio, com identidade que sobrevive a reinícios."""

    identidade: str
    origem: Origem
    chat_id: int
    estado: EstadoDoPedido = EstadoDoPedido.PENDENTE
    frase_reservada: str | None = None
    motivo_do_estado: str = "pedido criado"
    proxima_tentativa: datetime | None = None

    @property
    def estado_legado(self) -> str:
        """Vocabulário legível pelo worker anterior durante recuperação de versão."""
        if self.estado is EstadoDoPedido.RESERVADO:
            return "enviando"
        if self.estado is EstadoDoPedido.AGUARDANDO_TENTATIVA:
            return "enviando" if self.frase_reservada else "pendente"
        if self.estado is EstadoDoPedido.INCERTO:
            return "parcial"
        if self.estado is EstadoDoPedido.EXPIRADO:
            return "falhou"
        return str(self.estado.value)

    @staticmethod
    def identidade_de_extra(bot: str, update_id: int) -> str:
        """Identidade de um extra: o bot mais o update_id do Telegram (spec, 4.6)."""
        return f"extra#{bot}#{update_id}"

    @staticmethod
    def identidade_de_diaria(chat_id: int, dia: date) -> str:
        """Identidade de uma diária: conversa autorizada mais data local."""
        return f"diaria#{chat_id}#{dia.isoformat()}"

    @staticmethod
    def identidade_de_parte(pedido: str, indice: int) -> str:
        """Identidade de uma parte dentro de seu pedido."""
        return f"{pedido}#parte#{indice}"

    @staticmethod
    def identidade_de_tentativa(pedido: str, sequencial: int) -> str:
        """Identidade de uma tentativa dentro de seu pedido."""
        return f"{pedido}#tentativa#{sequencial}"

    def _transicionar(
        self,
        destino: EstadoDoPedido,
        motivo: str,
        *,
        frase_reservada: str | None,
    ) -> "Pedido":
        if not motivo.strip():
            raise ValueError("toda transição precisa de motivo")
        if self.estado.terminal:
            raise ValueError(f"pedido em estado terminal ({self.estado.value}) não muda")
        if destino not in _TRANSICOES_PERMITIDAS.get(self.estado, frozenset()):
            raise ValueError(f"transição inválida: {self.estado.value} -> {destino.value}")
        return replace(
            self,
            estado=destino,
            frase_reservada=frase_reservada,
            motivo_do_estado=motivo,
        )

    def reservar(self, frase: str) -> "Pedido":
        if not frase:
            raise ValueError("identidade da frase reservada não pode ser vazia")
        return self._transicionar(
            EstadoDoPedido.RESERVADO,
            "frase reservada",
            frase_reservada=frase,
        )

    def iniciar_envio(self) -> "Pedido":
        if self.estado not in (
            EstadoDoPedido.RESERVADO,
            EstadoDoPedido.AGUARDANDO_TENTATIVA,
        ):
            return self._transicionar(
                EstadoDoPedido.ENVIANDO,
                "envio iniciado",
                frase_reservada=self.frase_reservada,
            )
        if self.frase_reservada is None:
            raise ValueError("não é possível enviar pedido sem frase reservada")
        return self._transicionar(
            EstadoDoPedido.ENVIANDO,
            "envio iniciado",
            frase_reservada=self.frase_reservada,
        )

    def aguardar_tentativa(self, motivo: str) -> "Pedido":
        return self._transicionar(
            EstadoDoPedido.AGUARDANDO_TENTATIVA,
            motivo,
            frase_reservada=self.frase_reservada,
        )

    def liberar_frase_excluida(self, motivo: str) -> "Pedido":
        """Sai de uma reserva cuja frase sumiu da fonte, sem terminar o pedido.

        Só faz sentido antes de qualquer parte enviada: a frase é uma entrega
        lógica única, então trocar no meio de uma entrega parcial quebraria
        essa invariante (spec, 4.2/4.4) — quem chama garante isso checando o
        histórico de partes confirmadas antes de usar esta transição.
        Devolve a AGUARDANDO_TENTATIVA sem frase reservada, o mesmo estado de
        onde `reservar` já sabe partir para reservar outra elegível.
        """
        return self._transicionar(
            EstadoDoPedido.AGUARDANDO_TENTATIVA,
            motivo,
            frase_reservada=None,
        )

    def concluir(self) -> "Pedido":
        if self.frase_reservada is None:
            raise ValueError("não é possível concluir pedido sem frase reservada")
        return self._transicionar(
            EstadoDoPedido.ENVIADO,
            "todas as partes confirmadas",
            frase_reservada=self.frase_reservada,
        )

    def falhar(self, alguma_parte_enviada: bool, motivo: str) -> "Pedido":
        """Encerra o pedido sem sucesso.

        Falha comprovada sem nenhum envio libera a reserva. Entrega parcial mantém
        a frase consumida, para não reiniciar automaticamente algo que já pode ter
        chegado à usuária (spec, 4.4).
        """
        if alguma_parte_enviada:
            if self.frase_reservada is None:
                raise ValueError("entrega parcial precisa de frase reservada")
            return self._transicionar(
                EstadoDoPedido.PARCIAL,
                motivo,
                frase_reservada=self.frase_reservada,
            )
        return self._transicionar(
            EstadoDoPedido.FALHOU,
            motivo,
            frase_reservada=None,
        )

    def marcar_incerto(self, motivo: str) -> "Pedido":
        if self.frase_reservada is None:
            raise ValueError("entrega incerta precisa de frase reservada")
        return self._transicionar(
            EstadoDoPedido.INCERTO,
            motivo,
            frase_reservada=self.frase_reservada,
        )

    def expirar(self, motivo: str) -> "Pedido":
        return self._transicionar(
            EstadoDoPedido.EXPIRADO,
            motivo,
            frase_reservada=self.frase_reservada,
        )
