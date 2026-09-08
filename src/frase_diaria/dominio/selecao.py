from enum import Enum

from frase_diaria.aplicacao.portas import Sorteio
from frase_diaria.dominio.ciclo import Ciclo


class SemFrase(Enum):
    """Por que não há frase para entregar agora.

    A distinção decide o destino do pedido: uma é definitiva, a outra passa.
    """

    COLECAO_VAZIA = "colecao_vazia"
    AGUARDANDO_RESERVA = "aguardando_reserva"


def selecionar(
    ciclo: Ciclo, ativas: tuple[str, ...], sorteio: Sorteio
) -> tuple[str, Ciclo] | SemFrase:
    """Escolhe a próxima frase e devolve o ciclo com ela reservada.

    Reservar no mesmo passo é deliberado: uma seleção que não reserva abriria
    janela para dois pedidos escolherem a mesma frase.

    Quando não há o que entregar, o motivo importa. `COLECAO_VAZIA` é definitivo
    e encerra o pedido. `AGUARDANDO_RESERVA` é transitório — todas as frases
    foram consumidas mas uma segue reservada por um pedido em andamento — e o
    pedido deve esperar, não morrer. Reiniciar o ciclo aqui poria a frase
    reservada em dois ciclos ao mesmo tempo.
    """
    if ciclo.esgotado(ativas):
        ciclo = ciclo.reiniciar()

    candidatas = ciclo.candidatas_a_primeira(ativas)
    if candidatas:
        escolhida = sorteio.escolher(candidatas)
        return escolhida, ciclo.reservar(escolhida)

    return SemFrase.AGUARDANDO_RESERVA if ciclo.reservadas else SemFrase.COLECAO_VAZIA
