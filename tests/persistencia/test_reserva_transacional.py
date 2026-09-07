"""Reservar toca dois itens; ou os dois mudam, ou nenhum muda.

Uma gravação parcial deixaria o ciclo com uma frase reservada que pedido nenhum
conhece. Como `Ciclo.esgotado` exige ausência de reservas, o ciclo nunca
reiniciaria e o bot pararia de entregar em silêncio.
"""

from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from moto import mock_aws

from frase_diaria.dominio.ciclo import Ciclo
from frase_diaria.dominio.pedido import EstadoDoPedido, Origem, Pedido
from frase_diaria.persistencia.ciclos import RepositorioDeCiclosDynamo
from frase_diaria.persistencia.pedidos import RepositorioDePedidosDynamo
from frase_diaria.persistencia.reserva import ReservaTransacional

TABELA = "frase-diaria-estado-teste"
INSTANTE = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
PEDIDO = Pedido(identidade="extra#42", origem=Origem.EXTRA, chat_id=672024065)


@pytest.fixture
def contexto() -> Any:
    with mock_aws():
        dynamo = boto3.resource("dynamodb", region_name="us-east-1")
        dynamo.create_table(
            TableName=TABELA,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        tabela = dynamo.Table(TABELA)
        yield {
            "pedidos": RepositorioDePedidosDynamo(tabela=tabela),
            "ciclos": RepositorioDeCiclosDynamo(tabela=tabela),
            "reserva": ReservaTransacional(tabela=tabela),
        }


def test_efetivar_grava_ciclo_e_pedido(contexto: Any) -> None:
    contexto["pedidos"].criar_se_ausente(PEDIDO, INSTANTE)
    ciclo = Ciclo.primeiro().reservar("f1")

    contexto["reserva"].efetivar(PEDIDO.reservar("f1"), ciclo)

    assert contexto["ciclos"].carregar().reservadas == frozenset({"f1"})
    gravado = contexto["pedidos"].obter("extra#42")
    assert gravado is not None
    assert gravado.frase_reservada == "f1"
    assert gravado.estado is EstadoDoPedido.ENVIANDO


def test_pedido_inexistente_impede_a_reserva_inteira(contexto: Any) -> None:
    # A condição do pedido protege o ciclo: sem ela, o ciclo ficaria com uma
    # reserva órfã apontando para um pedido que não existe.
    ciclo = Ciclo.primeiro().reservar("f1")

    with pytest.raises(Exception, match="Transaction|Condition"):
        contexto["reserva"].efetivar(PEDIDO.reservar("f1"), ciclo)

    assert contexto["ciclos"].carregar().reservadas == frozenset()
