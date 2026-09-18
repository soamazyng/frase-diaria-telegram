"""O registro de comandos precisa ser idempotente sob concorrência.

O Telegram reentrega um update quando não recebe sucesso, e o reconciliador pode
processar em paralelo. Dois registros do mesmo update_id não podem virar dois
pedidos — a garantia vem de escrita condicional, não de "ler antes de gravar".
"""

import boto3
import pytest
from moto import mock_aws

from frase_diaria.dominio.autorizacao import Conversa
from frase_diaria.dominio.comando import Comando
from frase_diaria.persistencia.comandos import RepositorioDeComandosDynamo
from frase_diaria.telegram.atualizacao import Atualizacao

TABELA = "frase-diaria-estado-teste"
INSTANTE = __import__("datetime").datetime(2026, 9, 7, 12, 0, tzinfo=__import__("datetime").UTC)


def _atualizacao(update_id: int = 1, comando: Comando = Comando.FRASE) -> Atualizacao:
    return Atualizacao(
        update_id=update_id,
        conversa=Conversa(chat_id=111111, tipo="private"),
        comando=comando,
    )


@pytest.fixture
def repositorio():  # type: ignore[no-untyped-def]
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
        yield RepositorioDeComandosDynamo(tabela=dynamo.Table(TABELA))


def test_registra_um_comando_novo(repositorio) -> None:  # type: ignore[no-untyped-def]
    assert repositorio.registrar(_atualizacao(update_id=7), INSTANTE) is True


def test_o_mesmo_update_id_nao_registra_duas_vezes(repositorio) -> None:  # type: ignore[no-untyped-def]
    assert repositorio.registrar(_atualizacao(update_id=7), INSTANTE) is True
    assert repositorio.registrar(_atualizacao(update_id=7), INSTANTE) is False


def test_acao_e_reivindicada_uma_unica_vez_e_concluida(repositorio) -> None:  # type: ignore[no-untyped-def]
    repositorio.registrar(_atualizacao(update_id=7), INSTANTE)

    assert repositorio.reivindicar_acao(7) is True
    assert repositorio.reivindicar_acao(7) is False

    repositorio.marcar_acao_concluida(7)

    assert repositorio.reivindicar_acao(7) is False


def test_acao_definitivamente_recusada_pode_ser_reivindicada_de_novo(repositorio) -> None:  # type: ignore[no-untyped-def]
    repositorio.registrar(_atualizacao(update_id=7), INSTANTE)
    assert repositorio.reivindicar_acao(7) is True

    repositorio.liberar_acao(7)

    assert repositorio.reivindicar_acao(7) is True


def test_update_ids_diferentes_sao_registros_distintos(repositorio) -> None:  # type: ignore[no-untyped-def]
    assert repositorio.registrar(_atualizacao(update_id=7), INSTANTE) is True
    assert repositorio.registrar(_atualizacao(update_id=8), INSTANTE) is True


def test_o_registro_guarda_o_que_aconteceu(repositorio) -> None:  # type: ignore[no-untyped-def]
    repositorio.registrar(_atualizacao(update_id=7, comando=Comando.STATUS), INSTANTE)

    item = repositorio.tabela.get_item(Key={"pk": "comando#7", "sk": "registro"})["Item"]

    assert item["comando"] == "/status"
    assert item["chat_id"] == 111111
    assert item["recebido_em"] == "2026-09-07T12:00:00+00:00"


def test_repetir_nao_sobrescreve_o_registro_original(repositorio) -> None:  # type: ignore[no-untyped-def]
    repositorio.registrar(_atualizacao(update_id=7, comando=Comando.FRASE), INSTANTE)
    depois = __import__("datetime").datetime(2027, 1, 1, tzinfo=__import__("datetime").UTC)

    repositorio.registrar(_atualizacao(update_id=7, comando=Comando.STATUS), depois)

    item = repositorio.tabela.get_item(Key={"pk": "comando#7", "sk": "registro"})["Item"]
    assert item["comando"] == "/frase"
    assert item["recebido_em"] == "2026-09-07T12:00:00+00:00"


def test_falha_de_infraestrutura_propaga_em_vez_de_virar_sucesso(repositorio) -> None:  # type: ignore[no-untyped-def]
    repositorio.tabela.meta.client.meta.events.register(
        "before-call.dynamodb.PutItem",
        lambda **_: (_ for _ in ()).throw(RuntimeError("rede fora")),
    )

    with pytest.raises(RuntimeError):
        repositorio.registrar(_atualizacao(update_id=99), INSTANTE)
