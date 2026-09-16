from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from moto import mock_aws

from frase_diaria.persistencia.migrar_status import indexar_status_legado


@pytest.fixture
def tabela() -> Any:
    with mock_aws():
        dynamo = boto3.resource("dynamodb", region_name="us-east-1")
        criada = dynamo.create_table(
            TableName="estado-ficticio",
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
        yield criada


def test_indexa_entregas_confirmadas_e_incertas_sem_expor_conteudo(tabela: Any) -> None:
    instante = datetime(2026, 9, 7, 12, tzinfo=UTC).isoformat()
    for indice, estado in enumerate(("confirmada", "incerto")):
        tabela.put_item(
            Item={
                "pk": f"pedido#diaria#2026-09-0{indice + 5}",
                "sk": "parte#111111#000",
                "estado": estado,
                "destinatario": 111111,
                "texto": "conteúdo pessoal",
                "confirmada_em": instante,
            }
        )

    assert indexar_status_legado(tabela) == 2
    assert indexar_status_legado(tabela) == 0

    itens = tabela.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("pk").eq("status#111111")
    )["Items"]
    assert [item["sk"] for item in itens] == ["diaria#2026-09-05", "diaria#2026-09-06"]
    assert all("texto" not in item for item in itens)


def test_ignora_extras_partes_pendentes_e_itens_malformados(tabela: Any) -> None:
    for item in (
        {"pk": "pedido#extra#1", "sk": "parte#111111#000", "estado": "confirmada"},
        {
            "pk": "pedido#diaria#2026-09-05",
            "sk": "parte#111111#000",
            "estado": "intencao",
            "destinatario": 111111,
        },
        {"pk": "pedido#diaria#data-invalida", "sk": "parte#111111#000"},
    ):
        tabela.put_item(Item=item)

    assert indexar_status_legado(tabela) == 0


def test_indexa_diaria_v1_sem_estado_nem_destinatario_na_parte(tabela: Any) -> None:
    tabela.put_item(
        Item={
            "pk": "pedido#diaria#111111#2026-08-20",
            "sk": "parte#000",
            "indice": 0,
            "message_id": 900,
            "texto": "conteúdo histórico",
        }
    )

    assert indexar_status_legado(tabela) == 1

    item = tabela.get_item(Key={"pk": "status#111111", "sk": "diaria#2026-08-20"})["Item"]
    assert item == {
        "pk": "status#111111",
        "sk": "diaria#2026-08-20",
        "pedido": "diaria#111111#2026-08-20",
    }
