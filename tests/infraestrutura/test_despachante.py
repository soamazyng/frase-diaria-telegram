"""Acordar o worker é uma invocação assíncrona da Lambda dedicada.

Assíncrona porque a resposta HTTP do webhook não pode esperar a frase ser
entregue: o Telegram tem um limite curto de espera, e a spec descarta trabalho em
segundo plano depois de responder.
"""

import json
from typing import Any

from frase_diaria.infraestrutura.despachante import DespachanteLambda


class ClienteEspiao:
    def __init__(self) -> None:
        self.chamadas: list[dict[str, Any]] = []

    def invoke(self, **argumentos: Any) -> dict[str, Any]:
        self.chamadas.append(argumentos)
        return {"StatusCode": 202}


def test_invoca_a_funcao_worker_de_forma_assincrona() -> None:
    cliente = ClienteEspiao()

    DespachanteLambda(nome_da_funcao="frase-diaria-worker", cliente=cliente).acordar("extra#42")

    chamada = cliente.chamadas[0]
    assert chamada["FunctionName"] == "frase-diaria-worker"
    assert chamada["InvocationType"] == "Event"


def test_o_payload_carrega_apenas_a_identidade_do_pedido() -> None:
    # O worker relê o pedido da persistência; mandar o conteúdo junto abriria
    # espaço para processar um estado já desatualizado.
    cliente = ClienteEspiao()

    DespachanteLambda(nome_da_funcao="w", cliente=cliente).acordar("extra#42")

    assert json.loads(cliente.chamadas[0]["Payload"]) == {"pedido": "extra#42"}


def test_pedir_status_invoca_a_mesma_funcao_worker() -> None:
    # Mesma Lambda do envio de frase: já tem toda a permissão necessária, e uma
    # terceira função só para isto seria superfície de ataque sem benefício.
    cliente = ClienteEspiao()

    DespachanteLambda(nome_da_funcao="frase-diaria-worker", cliente=cliente).pedir_status(672024065)

    chamada = cliente.chamadas[0]
    assert chamada["FunctionName"] == "frase-diaria-worker"
    assert chamada["InvocationType"] == "Event"
    assert json.loads(chamada["Payload"]) == {"status_chat_id": 672024065}
