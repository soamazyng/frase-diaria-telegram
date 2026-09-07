from dataclasses import dataclass
from datetime import datetime

from frase_diaria.aplicacao.portas import CriadorDePedidos
from frase_diaria.dominio.pedido import Origem, Pedido
from frase_diaria.dominio.tempo import dia_local, em_utc


@dataclass(frozen=True)
class CriarDiaria:
    """Materializa o dia solicitado; o agendador será conectado no ticket 14."""

    pedidos: CriadorDePedidos
    chat_id: int

    def executar(self, instante_do_evento: datetime) -> str:
        instante = em_utc(instante_do_evento)
        pedido = Pedido(
            identidade=Pedido.identidade_de_diaria(self.chat_id, dia_local(instante)),
            origem=Origem.DIARIA,
            chat_id=self.chat_id,
            proxima_tentativa=instante,
        )
        self.pedidos.criar_se_ausente(pedido, instante)
        return pedido.identidade
