from dataclasses import dataclass
from datetime import datetime

from frase_diaria.aplicacao.portas import CriadorDePedidos
from frase_diaria.dominio.pedido import Origem, Pedido
from frase_diaria.dominio.tempo import dia_local, em_utc, prazo_da_diaria


@dataclass(frozen=True)
class CriarDiaria:
    """Materializa o pedido diário do dia local do instante do disparo.

    Chamada tanto pelo agendador quanto pelo reconciliador (ticket 14): a
    identidade (dia local, um único pedido para todos os destinatários — v2)
    torna as duas entradas idempotentes, então repetir a chamada nunca duplica
    a diária.
    """

    pedidos: CriadorDePedidos
    destinatarios: tuple[int, ...]

    def executar(self, instante_do_evento: datetime) -> str:
        instante = em_utc(instante_do_evento)
        dia = dia_local(instante)
        pedido = Pedido(
            identidade=Pedido.identidade_de_diaria(dia),
            origem=Origem.DIARIA,
            destinatarios=self.destinatarios,
            proxima_tentativa=instante,
            prazo=prazo_da_diaria(dia),
        )
        self.pedidos.criar_se_ausente(pedido, instante)
        return pedido.identidade
