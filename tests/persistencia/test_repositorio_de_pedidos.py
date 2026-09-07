"""Persistência de pedidos, partes e tentativas.

Partes e tentativas ficam em itens separados do pedido: o histórico cresce sem
limite conhecido, e um item único cresceria junto até bater no teto de 400 KB do
DynamoDB.
"""

from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from moto import mock_aws

from frase_diaria.dominio.pedido import EstadoDoPedido, Origem, Pedido
from frase_diaria.persistencia.pedidos import RepositorioDePedidosDynamo

TABELA = "frase-diaria-estado-teste"
INSTANTE = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
PEDIDO = Pedido(identidade="extra#42", origem=Origem.EXTRA, chat_id=672024065)


@pytest.fixture
def repositorio() -> Any:
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
        yield RepositorioDePedidosDynamo(tabela=dynamo.Table(TABELA))


def test_pedido_inexistente_devolve_none(repositorio: Any) -> None:
    assert repositorio.obter("extra#999") is None


def test_salva_e_recupera_preservando_o_estado(repositorio: Any) -> None:
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)

    repositorio.salvar(PEDIDO.reservar("bloco-7"))

    recuperado = repositorio.obter("extra#42")

    assert recuperado is not None
    assert recuperado.identidade == "extra#42"
    assert recuperado.origem is Origem.EXTRA
    assert recuperado.chat_id == 672024065
    assert recuperado.estado is EstadoDoPedido.ENVIANDO
    assert recuperado.frase_reservada == "bloco-7"


def test_criar_e_idempotente_por_identidade(repositorio: Any) -> None:
    assert repositorio.criar_se_ausente(PEDIDO, INSTANTE) is True
    assert repositorio.criar_se_ausente(PEDIDO, INSTANTE) is False


def test_criar_repetido_nao_desfaz_o_progresso(repositorio: Any) -> None:
    # Um /frase reentregue não pode devolver um pedido já em andamento à estaca zero.
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)
    repositorio.salvar(PEDIDO.reservar("bloco-7").concluir())

    repositorio.criar_se_ausente(PEDIDO, INSTANTE)

    assert repositorio.obter("extra#42").estado is EstadoDoPedido.ENVIADO


def test_confirma_partes_e_lista_os_indices(repositorio: Any) -> None:
    repositorio.confirmar_parte("extra#42", 0, "primeira", 901, INSTANTE)
    repositorio.confirmar_parte("extra#42", 1, "segunda", 902, INSTANTE)

    assert repositorio.indices_confirmados("extra#42") == {0, 1}


def test_a_parte_guarda_o_texto_efetivamente_enviado(repositorio: Any) -> None:
    repositorio.confirmar_parte("extra#42", 0, "o que a usuária recebeu", 901, INSTANTE)

    item = repositorio.tabela.get_item(Key={"pk": "pedido#extra#42", "sk": "parte#000"})["Item"]

    assert item["texto"] == "o que a usuária recebeu"
    assert item["message_id"] == 901


def test_partes_de_pedidos_distintos_nao_se_misturam(repositorio: Any) -> None:
    repositorio.confirmar_parte("extra#42", 0, "de um", 901, INSTANTE)
    repositorio.confirmar_parte("extra#43", 0, "de outro", 902, INSTANTE)

    assert repositorio.indices_confirmados("extra#42") == {0}
    assert repositorio.indices_confirmados("extra#43") == {0}


def test_tentativas_se_acumulam_em_itens_separados(repositorio: Any) -> None:
    repositorio.registrar_tentativa("extra#42", "falhou", "HTTP 500", INSTANTE)
    depois = datetime(2026, 9, 7, 12, 5, tzinfo=UTC)
    repositorio.registrar_tentativa("extra#42", "enviado", None, depois)

    itens = repositorio.tabela.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("pk").eq("pedido#extra#42")
        & boto3.dynamodb.conditions.Key("sk").begins_with("tentativa#")
    )["Items"]

    assert len(itens) == 2
    assert {i["resultado"] for i in itens} == {"falhou", "enviado"}


def test_salvar_nao_ressuscita_um_pedido_inexistente(repositorio: Any) -> None:
    """`update_item` faz upsert por padrão.

    Sem condição, salvar o estado de um pedido que nunca foi criado o inventaria
    na tabela — um item sem `criado_em`, invisível para quem espera a criação
    idempotente ter passado por `criar_se_ausente`.
    """
    fantasma = Pedido(identidade="extra#nunca-criado", origem=Origem.EXTRA, chat_id=1)

    with pytest.raises(Exception, match="ConditionalCheckFailed"):
        repositorio.salvar(fantasma.reservar("bloco-1"))

    assert repositorio.obter("extra#nunca-criado") is None


def test_leitura_do_pedido_e_fortemente_consistente(repositorio: Any) -> None:
    # O webhook cria o pedido e acorda o worker no mesmo instante; uma leitura
    # eventualmente consistente poderia não enxergar o item recém-gravado, e o
    # worker concluiria "pedido não encontrado" sem entregar nada.
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)

    assert repositorio.obter("extra#42") is not None
