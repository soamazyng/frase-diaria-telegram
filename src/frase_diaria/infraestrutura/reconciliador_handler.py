"""Entrada da Lambda periódica: recupera pendências a cada cinco minutos.

Alcança pedidos vencidos de qualquer origem (não só a diária) e, dentro da
janela até o meio-dia local, materializa a diária ausente — cobrindo tanto a
falha do disparo principal do agendador quanto um pedido preso por contenção
de ciclo (spec, 4.5).
"""

import logging
from typing import Any

from frase_diaria.infraestrutura.composicao import montar_reconciliar_pendencias

logging.getLogger().setLevel(logging.INFO)
_log = logging.getLogger(__name__)


def handler(evento: dict[str, Any], contexto: Any = None) -> dict[str, Any]:
    acordados = montar_reconciliar_pendencias().executar()
    _log.info("reconciliador acordou %d pedido(s) vencido(s)", acordados)
    return {"acordados": acordados}
