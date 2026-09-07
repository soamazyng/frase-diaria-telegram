"""O estado do ciclo precisa sobreviver a reinícios da aplicação.

Cada Lambda que atende um `/frase` é um processo novo: se o ciclo vivesse em
memória, toda entrega recomeçaria do zero e a coleção nunca seria percorrida.
"""

from typing import Any

import boto3
import pytest
from moto import mock_aws

from frase_diaria.dominio.ciclo import Ciclo
from frase_diaria.persistencia.ciclos import RepositorioDeCiclosDynamo

TABELA = "frase-diaria-estado-teste"
TODAS = ("a", "b", "c")


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
        yield RepositorioDeCiclosDynamo(tabela=dynamo.Table(TABELA))


def test_sem_ciclo_gravado_comeca_do_primeiro(repositorio: Any) -> None:
    ciclo = repositorio.carregar()

    assert ciclo.numero == 1
    assert ciclo.elegiveis(TODAS) == TODAS


def test_o_consumo_sobrevive_a_um_reinicio(repositorio: Any) -> None:
    repositorio.salvar(Ciclo.primeiro().reservar("a").consumir("a"))

    recarregado = repositorio.carregar()

    assert recarregado.foi_consumida("a")
    assert recarregado.elegiveis(TODAS) == ("b", "c")
    assert recarregado.ultima_entregue == "a"


def test_a_reserva_sobrevive_a_um_reinicio(repositorio: Any) -> None:
    # Sem isso, um pedido interrompido perderia a reserva e outro poderia sortear
    # a mesma frase.
    repositorio.salvar(Ciclo.primeiro().reservar("b"))

    recarregado = repositorio.carregar()

    assert recarregado.elegiveis(TODAS) == ("a", "c")
    assert not recarregado.foi_consumida("b")


def test_a_ressalva_sobrevive_a_um_reinicio(repositorio: Any) -> None:
    repositorio.salvar(Ciclo.primeiro().reservar("b").consumir("b", com_ressalva=True))

    recarregado = repositorio.carregar()

    assert recarregado.consumidas_com_ressalva == frozenset({"b"})


def test_ciclo_reiniciado_e_persistido_com_o_numero_novo(repositorio: Any) -> None:
    ciclo = Ciclo.primeiro()
    for frase in TODAS:
        ciclo = ciclo.reservar(frase).consumir(frase)
    repositorio.salvar(ciclo.reiniciar())

    recarregado = repositorio.carregar()

    assert recarregado.numero == 2
    assert recarregado.elegiveis(TODAS) == TODAS
    assert recarregado.ultima_entregue == "c"


def test_conjuntos_vazios_nao_quebram_a_gravacao(repositorio: Any) -> None:
    # O DynamoDB recusa conjuntos vazios; um ciclo recém-aberto tem três deles.
    repositorio.salvar(Ciclo.primeiro())

    recarregado = repositorio.carregar()

    assert recarregado.consumidas == frozenset()
    assert recarregado.reservadas == frozenset()
    assert recarregado.consumidas_com_ressalva == frozenset()


def test_ciclo_completo_faz_a_volta_toda_sem_perder_nada(repositorio: Any) -> None:
    ciclo = repositorio.carregar()
    for frase in TODAS:
        ciclo = ciclo.reservar(frase)
        repositorio.salvar(ciclo)
        ciclo = repositorio.carregar().consumir(frase)
        repositorio.salvar(ciclo)

    final = repositorio.carregar()

    assert final.esgotado(TODAS)
    assert final.consumidas == frozenset(TODAS)
    assert final.entregas_neste_ciclo == 3
