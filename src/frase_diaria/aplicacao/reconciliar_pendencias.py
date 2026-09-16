import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from frase_diaria.aplicacao.portas import Relogio
from frase_diaria.dominio.pedido import Pedido
from frase_diaria.dominio.tempo import (
    FUSO_LOCAL,
    INICIO_DO_ENVIO_ALVO_LOCAL,
    LIMITE_DE_RECUPERACAO_LOCAL,
)

_log = logging.getLogger(__name__)


class RepositorioDePendencias(Protocol):
    def buscar_vencidos(self, instante: datetime) -> list[Pedido]: ...


class DespachanteDeWorker(Protocol):
    def acordar(self, identidade: str) -> None: ...


class CriadorDeDiaria(Protocol):
    def executar(self, instante_do_evento: datetime) -> str: ...


@dataclass(frozen=True)
class ReconciliarPendencias:
    """Alcança o que o disparo principal do agendador não alcançou.

    Cobre dois casos: pedidos vencidos de qualquer origem — não só a diária,
    pois um `/frase` pode ficar preso em AGUARDANDO_TENTATIVA por contenção de
    ciclo (achado do ticket 06) — e a diária ausente dentro da janela até o
    meio-dia local, quando o disparo principal do agendador falhou.
    """

    pedidos: RepositorioDePendencias
    despachante: DespachanteDeWorker
    diaria: CriadorDeDiaria
    relogio: Relogio

    def executar(self) -> int:
        agora = self.relogio.agora()

        if self._dentro_da_janela_de_recuperacao(agora):
            try:
                self.diaria.executar(agora)
            except Exception:
                # A idempotência é por identidade (dia local — v2: um único
                # pedido para todos os destinatários, não mais por conversa):
                # a próxima varredura, cinco minutos depois, tenta de novo.
                _log.error(
                    "falha ao materializar a diária ausente; próxima varredura tenta de novo"
                )

        acordados = 0
        for pedido in self.pedidos.buscar_vencidos(agora):
            try:
                self.despachante.acordar(pedido.identidade)
                acordados += 1
            except Exception:
                # Uma falha pontual de despacho não pode travar a varredura dos
                # demais pedidos vencidos; o pedido permanece persistido e volta
                # a aparecer na próxima varredura.
                _log.error("falha ao acordar pedido vencido; próxima varredura tenta de novo")
        return acordados

    def _dentro_da_janela_de_recuperacao(self, agora: datetime) -> bool:
        hora_local = agora.astimezone(FUSO_LOCAL).time()
        return INICIO_DO_ENVIO_ALVO_LOCAL <= hora_local < LIMITE_DE_RECUPERACAO_LOCAL
