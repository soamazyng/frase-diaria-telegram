"""Entrada da Lambda agendada: dispara a diária às 08:00 America/Sao_Paulo.

O EventBridge Scheduler resolve o fuso — o horário-alvo é declarado como está,
sem conversão manual para UTC (infra/aplicacao.yaml). Separada do worker e do
reconciliador de propósito: cada função tem só a permissão que usa.
"""

import logging
from typing import Any

from frase_diaria.infraestrutura.composicao import montar_criar_diaria, montar_despachante
from frase_diaria.infraestrutura.relogio import RelogioDoSistema

logging.getLogger().setLevel(logging.INFO)
_log = logging.getLogger(__name__)


def handler(evento: dict[str, Any], contexto: Any = None) -> dict[str, Any]:
    identidade = montar_criar_diaria().executar(RelogioDoSistema().agora())
    montar_despachante().acordar(identidade)
    _log.info("diária materializada e worker acordado")
    return {"pedido": identidade}
