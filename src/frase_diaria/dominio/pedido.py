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


# Motivo de um pedido recém-criado, antes de qualquer transição. Constante
# compartilhada (não só o default do campo abaixo) porque `telegram/status.py`
# precisa reconhecer esse motivo para não exibi-lo como se fosse informativo.
MOTIVO_PADRAO = "pedido criado"

# Textos compartilhados pelas transições e pelo diagnóstico individual.
MOTIVO_FRASE_RESERVADA = "frase reservada"
MOTIVO_ENVIO_INICIADO = "envio iniciado"
MOTIVO_TODAS_AS_PARTES_CONFIRMADAS = "todas as partes confirmadas"


@dataclass(frozen=True)
class Pedido:
    """Uma solicitação de envio, com identidade que sobrevive a reinícios.

    `destinatarios` é quem recebe esta entrega: um extra tem exatamente um
    (quem pediu); a diária carrega todos os destinatários autorizados,
    compartilhando uma única reserva/consumo de frase no ciclo (spec v2,
    `.scratch/v2-telegram-bot.md`).
    """

    identidade: str
    origem: Origem
    destinatarios: tuple[int, ...]
    estado: EstadoDoPedido = EstadoDoPedido.PENDENTE
    frase_reservada: str | None = None
    motivo_do_estado: str = MOTIVO_PADRAO
    proxima_tentativa: datetime | None = None
    # Instante-limite (UTC) após o qual o pedido é abandonado em vez de retentado.
    # None significa "sem prazo conhecido" — só ocorre em pedidos persistidos
    # antes deste campo existir, ou num extra de tentativa única (abaixo), cujo
    # prazo não é uma data: é a ausência de qualquer retentativa.
    prazo: datetime | None = None
    # Um extra criado a partir do meio-dia local tem uma tentativa imediata, sem
    # retentativa nenhuma — nem mesmo diante de um erro transitório do Telegram
    # (spec, 4.5). `prazo` não expressa isso: o despacho é sempre um pouco
    # posterior à criação, e um prazo próximo dela seria ultrapassado antes da
    # própria tentativa única rodar.
    tentativa_unica: bool = False
    total_de_partes: int | None = None
    partes_reservadas: tuple[str, ...] | None = None
    destinatarios_com_falha: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.destinatarios:
            raise ValueError("pedido precisa de ao menos um destinatário")

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
    def identidade_de_diaria(dia: date) -> str:
        """Identidade de uma diária: um único pedido por dia local.

        Até a v1, incluía o chat_id (`diaria#<chat_id>#<dia>`) — a v2 entrega a
        mesma frase a todos os destinatários autorizados a partir de um único
        pedido, então o chat_id deixou de fazer parte da identidade. Identidades
        no formato antigo permanecem como histórico, sem serem reprocessadas.
        """
        return f"diaria#{dia.isoformat()}"

    def dia_alvo_da_diaria(self) -> date | None:
        """O dia local que esta diária alvejava, ou `None` para um extra.

        Lido de volta da própria identidade — nenhum campo novo precisa ser
        persistido só para isto (`/status` usa este dia para relatar "quando"
        foi o último envio confirmado).
        """
        if self.origem is not Origem.DIARIA:
            return None
        return date.fromisoformat(self.identidade.rsplit("#", 1)[-1])

    @staticmethod
    def identidade_de_parte(pedido: str, destinatario: int, indice: int) -> str:
        """Identidade de uma parte: pedido, destinatário e índice.

        Até a v1 era só pedido + índice — um pedido tinha um único
        destinatário. A partir da v2, a mesma parte de um pedido compartilhado
        pode ter desfechos diferentes por destinatário (confirmada para um,
        incerta para outro), então o destinatário passa a fazer parte da
        identidade (spec v2, `.scratch/v2-telegram-bot.md`).
        """
        return f"{pedido}#dest#{destinatario}#parte#{indice}"

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
            MOTIVO_FRASE_RESERVADA,
            frase_reservada=frase,
        )

    def iniciar_envio(self) -> "Pedido":
        if self.estado not in (
            EstadoDoPedido.RESERVADO,
            EstadoDoPedido.AGUARDANDO_TENTATIVA,
        ):
            return self._transicionar(
                EstadoDoPedido.ENVIANDO,
                MOTIVO_ENVIO_INICIADO,
                frase_reservada=self.frase_reservada,
            )
        if self.frase_reservada is None:
            raise ValueError("não é possível enviar pedido sem frase reservada")
        return self._transicionar(
            EstadoDoPedido.ENVIANDO,
            MOTIVO_ENVIO_INICIADO,
            frase_reservada=self.frase_reservada,
        )

    def aguardar_tentativa(
        self, motivo: str, proxima_tentativa: datetime | None = None
    ) -> "Pedido":
        """Sai de circulação até `proxima_tentativa`, sem perder a reserva.

        Sem um `proxima_tentativa` explícito, o instante já persistido é mantido
        — é o caso da retentativa por contenção de ciclo (ticket 09), que não
        precisa de espera progressiva. Um erro transitório do Telegram (ticket
        14) passa o instante calculado com a espera progressiva.
        """
        pedido = self._transicionar(
            EstadoDoPedido.AGUARDANDO_TENTATIVA,
            motivo,
            frase_reservada=self.frase_reservada,
        )
        if proxima_tentativa is not None:
            pedido = replace(pedido, proxima_tentativa=proxima_tentativa)
        return pedido

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
            MOTIVO_TODAS_AS_PARTES_CONFIRMADAS,
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
        """Abandona o pedido sem que nada tenha sido entregue.

        Libera a reserva, como `falhar(alguma_parte_enviada=False)` — mesma
        regra, "nada enviado libera a frase" (spec, 4.4). Quando alguma parte já
        foi confirmada, o encerramento correto é `falhar(alguma_parte_enviada=True)`
        (PARCIAL), não este.
        """
        return self._transicionar(
            EstadoDoPedido.EXPIRADO,
            motivo,
            frase_reservada=None,
        )
