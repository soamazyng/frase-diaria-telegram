"""Entrada da Lambda worker.

Separada da entrada HTTP de propósito: o worker é acionado por invocação
assíncrona e, mais adiante, pelo agendador — nunca por API Gateway. Manter as
duas entradas distintas evita que o formato de evento de uma vaze na outra.
"""

import logging
from typing import Any

from frase_diaria.infraestrutura.composicao import montar_processar_pedido

logging.getLogger().setLevel(logging.INFO)
_log = logging.getLogger(__name__)


def handler(evento: dict[str, Any], contexto: Any = None) -> dict[str, Any]:
    identidade = evento.get("pedido")
    if not isinstance(identidade, str) or not identidade:
        _log.error("evento sem identidade de pedido")
        return {"processado": False, "motivo": "evento inválido"}

    pedido = montar_processar_pedido().executar(identidade)
    if pedido is None:
        # Levantar, e não devolver sucesso: a invocação assíncrona só é
        # reentregue se o handler falhar. Devolver sucesso aqui transformaria um
        # atraso de propagação numa frase nunca entregue.
        raise RuntimeError("pedido não encontrado")

    _log.info("pedido terminou em %s", pedido.estado.value)
    return {"processado": True, "estado": pedido.estado.value}
