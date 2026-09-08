"""O estado do ciclo precisa sobreviver a reinícios da aplicação.

Cada Lambda que atende um `/frase` é um processo novo: se o ciclo vivesse em
memória, toda entrega recomeçaria do zero e a coleção nunca seria percorrida.

Diárias e extras compartilham o mesmo item, então dois executores podem
carregá-lo ao mesmo tempo — é o que a versão concorrente protege (ticket 09).
"""

from typing import Any

import boto3
import pytest
from moto import mock_aws

from frase_diaria.aplicacao.portas import ConflitoDeConcorrencia
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
    ciclo, versao = repositorio.carregar()

    assert ciclo.numero == 1
    assert ciclo.elegiveis(TODAS) == TODAS
    assert versao == 0


def test_o_consumo_sobrevive_a_um_reinicio(repositorio: Any) -> None:
    repositorio.salvar(Ciclo.primeiro().reservar("a").consumir("a"), 0)

    recarregado, _ = repositorio.carregar()

    assert recarregado.foi_consumida("a")
    assert recarregado.elegiveis(TODAS) == ("b", "c")
    assert recarregado.ultima_entregue == "a"


def test_a_reserva_sobrevive_a_um_reinicio(repositorio: Any) -> None:
    # Sem isso, um pedido interrompido perderia a reserva e outro poderia sortear
    # a mesma frase.
    repositorio.salvar(Ciclo.primeiro().reservar("b"), 0)

    recarregado, _ = repositorio.carregar()

    assert recarregado.elegiveis(TODAS) == ("a", "c")
    assert not recarregado.foi_consumida("b")


def test_a_ressalva_sobrevive_a_um_reinicio(repositorio: Any) -> None:
    repositorio.salvar(Ciclo.primeiro().reservar("b").consumir("b", com_ressalva=True), 0)

    recarregado, _ = repositorio.carregar()

    assert recarregado.consumidas_com_ressalva == frozenset({"b"})


def test_ciclo_reiniciado_e_persistido_com_o_numero_novo(repositorio: Any) -> None:
    ciclo = Ciclo.primeiro()
    for frase in TODAS:
        ciclo = ciclo.reservar(frase).consumir(frase)
    repositorio.salvar(ciclo.reiniciar(), 0)

    recarregado, _ = repositorio.carregar()

    assert recarregado.numero == 2
    assert recarregado.elegiveis(TODAS) == TODAS
    assert recarregado.ultima_entregue == "c"


def test_conjuntos_vazios_nao_quebram_a_gravacao(repositorio: Any) -> None:
    # O DynamoDB recusa conjuntos vazios; um ciclo recém-aberto tem três deles.
    repositorio.salvar(Ciclo.primeiro(), 0)

    recarregado, _ = repositorio.carregar()

    assert recarregado.consumidas == frozenset()
    assert recarregado.reservadas == frozenset()
    assert recarregado.consumidas_com_ressalva == frozenset()


def test_ciclo_completo_faz_a_volta_toda_sem_perder_nada(repositorio: Any) -> None:
    ciclo, versao = repositorio.carregar()
    for frase in TODAS:
        ciclo = ciclo.reservar(frase)
        repositorio.salvar(ciclo, versao)
        ciclo, versao = repositorio.carregar()
        ciclo = ciclo.consumir(frase)
        repositorio.salvar(ciclo, versao)
        ciclo, versao = repositorio.carregar()

    final, _ = repositorio.carregar()

    assert final.esgotado(TODAS)
    assert final.consumidas == frozenset(TODAS)
    assert final.entregas_neste_ciclo == 3


# --- concorrência (ticket 09) -------------------------------------------------


def test_a_versao_avanca_a_cada_gravacao(repositorio: Any) -> None:
    repositorio.salvar(Ciclo.primeiro().reservar("a"), 0)
    _, versao_1 = repositorio.carregar()
    repositorio.salvar(Ciclo.primeiro().reservar("a").consumir("a"), versao_1)
    _, versao_2 = repositorio.carregar()

    assert versao_1 == 1
    assert versao_2 == 2


def test_gravar_com_versao_desatualizada_e_recusado(repositorio: Any) -> None:
    # Dois executores carregam o mesmo ciclo (versão 0); o primeiro grava e
    # avança para 1. O segundo, ainda com a versão antiga em mãos, não pode
    # sobrescrever a reserva que o primeiro acabou de gravar.
    ciclo, versao = repositorio.carregar()
    executor_a = ciclo.reservar("a")
    executor_b = ciclo.reservar("b")

    repositorio.salvar(executor_a, versao)

    with pytest.raises(ConflitoDeConcorrencia):
        repositorio.salvar(executor_b, versao)

    # A reserva do vencedor sobrevive intacta; a do perdedor nunca chegou à tabela.
    final, versao_final = repositorio.carregar()
    assert final.reservadas == frozenset({"a"})
    assert versao_final == 1


def test_apos_o_conflito_reler_e_gravar_de_novo_funciona(repositorio: Any) -> None:
    # É o que permite a uma execução interrompida ser retomada sem bloqueio
    # permanente: reler a versão vigente e tentar de novo com ela.
    ciclo, versao = repositorio.carregar()
    repositorio.salvar(ciclo.reservar("a"), versao)

    with pytest.raises(ConflitoDeConcorrencia):
        repositorio.salvar(ciclo.reservar("b"), versao)

    recarregado, versao_atual = repositorio.carregar()
    repositorio.salvar(recarregado.reservar("b"), versao_atual)

    final, _ = repositorio.carregar()
    assert final.reservadas == frozenset({"a", "b"})
