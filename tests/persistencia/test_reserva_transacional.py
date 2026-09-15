"""Reservar toca dois itens; ou os dois mudam, ou nenhum muda.

Uma gravação parcial deixaria o ciclo com uma frase reservada que pedido nenhum
conhece. Como `Ciclo.esgotado` exige ausência de reservas, o ciclo nunca
reiniciaria e o bot pararia de entregar em silêncio.

A condição de versão no ciclo e de lease no pedido é o que decide, entre dois
executores concorrentes, qual dos dois efetiva a reserva (ticket 09).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from moto import mock_aws

from frase_diaria.aplicacao.portas import ConflitoDeConcorrencia
from frase_diaria.dominio.ciclo import Ciclo
from frase_diaria.dominio.pedido import EstadoDoPedido, Origem, Pedido
from frase_diaria.persistencia.ciclos import RepositorioDeCiclosDynamo
from frase_diaria.persistencia.pedidos import RepositorioDePedidosDynamo
from frase_diaria.persistencia.reserva import ReservaTransacional

TABELA = "frase-diaria-estado-teste"
INSTANTE = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
PEDIDO = Pedido(identidade="extra#42", origem=Origem.EXTRA, destinatarios=(672024065,))


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

    contexto["reserva"].efetivar(PEDIDO.reservar("f1"), ciclo, 0, sequencial=1)

    ciclo_gravado, versao = contexto["ciclos"].carregar()
    assert ciclo_gravado.reservadas == frozenset({"f1"})
    assert versao == 1
    gravado = contexto["pedidos"].obter("extra#42")
    assert gravado is not None
    assert gravado.frase_reservada == "f1"
    assert gravado.estado is EstadoDoPedido.RESERVADO


def test_pedido_inexistente_impede_a_reserva_inteira(contexto: Any) -> None:
    # A condição do pedido protege o ciclo: sem ela, o ciclo ficaria com uma
    # reserva órfã apontando para um pedido que não existe.
    ciclo = Ciclo.primeiro().reservar("f1")

    with pytest.raises(ConflitoDeConcorrencia):
        contexto["reserva"].efetivar(PEDIDO.reservar("f1"), ciclo, 0, sequencial=1)

    assert contexto["ciclos"].carregar()[0].reservadas == frozenset()


# --- concorrência (ticket 09) -------------------------------------------------


def test_dois_executores_disputando_a_mesma_versao_do_ciclo_so_um_vence(contexto: Any) -> None:
    contexto["pedidos"].criar_se_ausente(PEDIDO, INSTANTE)
    ciclo, versao = contexto["ciclos"].carregar()

    # Os dois leram a mesma versão do ciclo e sortearam frases diferentes.
    contexto["reserva"].efetivar(PEDIDO.reservar("f1"), ciclo.reservar("f1"), versao, sequencial=1)
    with pytest.raises(ConflitoDeConcorrencia):
        contexto["reserva"].efetivar(
            PEDIDO.reservar("f2"), ciclo.reservar("f2"), versao, sequencial=2
        )

    ciclo_final, _ = contexto["ciclos"].carregar()
    assert ciclo_final.reservadas == frozenset({"f1"})
    gravado = contexto["pedidos"].obter("extra#42")
    assert gravado is not None
    assert gravado.frase_reservada == "f1"


def test_lease_do_pedido_impede_reserva_por_um_sequencial_mais_antigo(contexto: Any) -> None:
    # Um sequencial maior já assumiu o lease do pedido (ex.: o mesmo evento
    # entregue duas vezes pela invocação assíncrona da Lambda); a tentativa mais
    # antiga não pode mais efetivar reserva nenhuma para este pedido (AC03).
    contexto["pedidos"].criar_se_ausente(PEDIDO, INSTANTE)
    contexto["pedidos"].assumir_lease(
        "extra#42", sequencial=2, agora=INSTANTE, duracao=timedelta(minutes=5)
    )
    ciclo, versao = contexto["ciclos"].carregar()

    with pytest.raises(ConflitoDeConcorrencia):
        contexto["reserva"].efetivar(
            PEDIDO.reservar("f1"), ciclo.reservar("f1"), versao, sequencial=1
        )

    assert contexto["ciclos"].carregar()[0].reservadas == frozenset()
