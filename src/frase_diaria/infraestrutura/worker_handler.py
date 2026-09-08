"""Entrada da Lambda worker.

Separada da entrada HTTP de propósito: o worker é acionado por invocação
assíncrona — pela fronteira HTTP, pelo agendador ou pelo reconciliador — nunca
por API Gateway. Manter as entradas distintas evita que o formato de evento de
uma vaze na outra.

Dois formatos de evento chegam aqui, distinguidos pela chave presente:
`{"pedido": <identidade>}` entrega uma frase; `{"status_chat_id": <chat_id>}`
monta e envia o relatório de `/status`. Nenhum dos dois é uma "pendência"
persistida com retry próprio — o status não tem identidade nem confirmação
durável, então uma reentrega da invocação assíncrona apenas reenvia a mesma
resposta informativa.
"""

import logging
from typing import Any

from frase_diaria.infraestrutura.composicao import montar_enviar_status, montar_processar_pedido

logging.getLogger().setLevel(logging.INFO)
_log = logging.getLogger(__name__)


def handler(evento: dict[str, Any], contexto: Any = None) -> dict[str, Any]:
    identidade = evento.get("pedido")
    if isinstance(identidade, str) and identidade:
        return _processar_pedido(identidade)

    chat_id = evento.get("status_chat_id")
    if isinstance(chat_id, int):
        return _enviar_status(chat_id)

    _log.error("evento não reconhecido: nem pedido, nem status_chat_id")
    return {"processado": False, "motivo": "evento inválido"}


def _processar_pedido(identidade: str) -> dict[str, Any]:
    pedido = montar_processar_pedido().executar(identidade)
    if pedido is None:
        # Levantar, e não devolver sucesso: a invocação assíncrona só é
        # reentregue se o handler falhar. Devolver sucesso aqui transformaria um
        # atraso de propagação numa frase nunca entregue.
        raise RuntimeError("pedido não encontrado")

    _log.info("pedido terminou em %s", pedido.estado.value)
    return {"processado": True, "estado": pedido.estado.value}


def _enviar_status(chat_id: int) -> dict[str, Any]:
    montar_enviar_status(chat_id).executar()
    _log.info("status enviado")
    return {"processado": True}
