"""Persistência de pedidos, partes e tentativas.

Partes e tentativas ficam em itens separados do pedido: o histórico cresce sem
limite conhecido, e um item único cresceria junto até bater no teto de 400 KB do
DynamoDB.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import boto3
import pytest
from moto import mock_aws

from frase_diaria.aplicacao.criar_diaria import CriarDiaria
from frase_diaria.aplicacao.portas import ConflitoDeConcorrencia
from frase_diaria.dominio.pedido import EstadoDoPedido, Origem, Pedido
from frase_diaria.persistencia.migrar_pendencias import indexar_pedidos_legados
from frase_diaria.persistencia.pedidos import RepositorioDePedidosDynamo

TABELA = "frase-diaria-estado-teste"
INSTANTE = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
PEDIDO = Pedido(
    identidade="extra#bot-ficticio#42",
    origem=Origem.EXTRA,
    chat_id=123456789,
)


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
                {"AttributeName": "pendencia", "AttributeType": "S"},
                {"AttributeName": "processar_em", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "pendencias",
                    "KeySchema": [
                        {"AttributeName": "pendencia", "KeyType": "HASH"},
                        {"AttributeName": "processar_em", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "KEYS_ONLY"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield RepositorioDePedidosDynamo(tabela=dynamo.Table(TABELA))


def test_pedido_inexistente_devolve_none(repositorio: Any) -> None:
    assert repositorio.obter("extra#999") is None


def test_salva_e_recupera_preservando_o_estado(repositorio: Any) -> None:
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)

    repositorio.salvar(PEDIDO.reservar("bloco-7"))

    recuperado = repositorio.obter("extra#bot-ficticio#42")

    assert recuperado is not None
    assert recuperado.identidade == "extra#bot-ficticio#42"
    assert recuperado.origem is Origem.EXTRA
    assert recuperado.chat_id == 123456789
    assert recuperado.estado is EstadoDoPedido.RESERVADO
    assert recuperado.frase_reservada == "bloco-7"
    assert recuperado.motivo_do_estado == "frase reservada"


def test_criar_e_idempotente_por_identidade(repositorio: Any) -> None:
    assert repositorio.criar_se_ausente(PEDIDO, INSTANTE) is True
    assert repositorio.criar_se_ausente(PEDIDO, INSTANTE) is False


def test_criar_repetido_nao_desfaz_o_progresso(repositorio: Any) -> None:
    # Um /frase reentregue não pode devolver um pedido já em andamento à estaca zero.
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)
    repositorio.salvar(PEDIDO.reservar("bloco-7").iniciar_envio().concluir())

    repositorio.criar_se_ausente(PEDIDO, INSTANTE)

    assert repositorio.obter(PEDIDO.identidade).estado is EstadoDoPedido.ENVIADO


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


def test_tentativas_no_mesmo_instante_tem_sequencia_e_metadados(repositorio: Any) -> None:
    repositorio.registrar_tentativa("pedido-ficticio", "erro", "token=SECRETO", INSTANTE)
    repositorio.registrar_tentativa("pedido-ficticio", "enviado", None, INSTANTE)

    tentativas = repositorio.listar_tentativas("pedido-ficticio")

    assert [t["sequencial"] for t in tentativas] == [1, 2]
    assert tentativas[0]["identidade"] == "pedido-ficticio#tentativa#1"
    assert tentativas[0]["erro"] == "erro de integração"
    assert tentativas[0]["ocorrida_em"] == "2026-09-07T12:00:00.000000+00:00"
    assert all(t["versao"] and t["correlacao"] for t in tentativas)


def test_pendencias_vencidas_excluem_futuras_e_terminais(repositorio: Any) -> None:
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)
    futuro = replace(PEDIDO, identidade="futuro", proxima_tentativa=INSTANTE + timedelta(hours=1))
    repositorio.criar_se_ausente(futuro, INSTANTE)

    assert [p.identidade for p in repositorio.buscar_vencidos(INSTANTE)] == [PEDIDO.identidade]

    repositorio.salvar(PEDIDO.reservar("f1").iniciar_envio().concluir())
    assert repositorio.buscar_vencidos(INSTANTE) == []
    assert [p.identidade for p in repositorio.buscar_vencidos(INSTANTE + timedelta(hours=2))] == [
        "futuro"
    ]


def test_instantes_sao_normalizados_para_utc(repositorio: Any) -> None:
    local = datetime(2026, 9, 7, 9, tzinfo=timezone(timedelta(hours=-3)))
    pedido = replace(PEDIDO, proxima_tentativa=local)
    repositorio.criar_se_ausente(pedido, local)

    recuperado = repositorio.obter(PEDIDO.identidade)

    assert recuperado.proxima_tentativa == INSTANTE
    assert recuperado.proxima_tentativa.tzinfo is UTC


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


def test_leitura_do_pedido_e_fortemente_consistente(
    repositorio: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # O webhook cria o pedido e acorda o worker no mesmo instante; uma leitura
    # eventualmente consistente poderia não enxergar o item recém-gravado, e o
    # worker concluiria "pedido não encontrado" sem entregar nada.
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)
    get_item_real = repositorio.tabela.get_item
    chamadas: list[dict[str, Any]] = []

    def get_item_espiado(**argumentos: Any) -> Any:
        chamadas.append(argumentos)
        return get_item_real(**argumentos)

    monkeypatch.setattr(repositorio.tabela, "get_item", get_item_espiado)

    assert repositorio.obter("extra#bot-ficticio#42") is not None
    assert chamadas == [
        {
            "Key": {"pk": "pedido#extra#bot-ficticio#42", "sk": "pedido"},
            "ConsistentRead": True,
        }
    ]


def test_diaria_repetida_usa_o_dia_local_e_preserva_terminal(repositorio: Any) -> None:
    evento = datetime(2026, 9, 8, 2, tzinfo=UTC)
    criar = CriarDiaria(repositorio, chat_id=123456789)
    identidade = criar.executar(evento)
    pedido = repositorio.obter(identidade)
    repositorio.salvar(pedido.reservar("f1").iniciar_envio().concluir())

    assert criar.executar(evento) == "diaria#123456789#2026-09-07"
    assert repositorio.obter(identidade).estado is EstadoDoPedido.ENVIADO


def test_gravacao_atrasada_nao_reabre_terminal(repositorio: Any) -> None:
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)
    atrasado = repositorio.obter(PEDIDO.identidade).reservar("f1")
    repositorio.salvar(atrasado.iniciar_envio().concluir())

    with pytest.raises(Exception, match="ConditionalCheckFailed"):
        repositorio.salvar(atrasado)

    assert repositorio.obter(PEDIDO.identidade).estado is EstadoDoPedido.ENVIADO


def test_chave_do_bot_original_preserva_leitura_e_replay_da_versao_anterior(
    repositorio: Any,
) -> None:
    atual = RepositorioDePedidosDynamo(repositorio.tabela, bot_legado="bot-ficticio")
    assert atual.criar_se_ausente(PEDIDO, INSTANTE)
    atual.salvar(PEDIDO.reservar("f1"))
    item = repositorio.tabela.get_item(Key={"pk": "pedido#extra#42", "sk": "pedido"})["Item"]

    assert item["identidade"] == "extra#42"
    assert item["estado"] == "enviando"
    recuperado = atual.obter(PEDIDO.identidade)
    assert recuperado is not None
    assert recuperado.estado is EstadoDoPedido.RESERVADO
    assert not repositorio.criar_se_ausente(replace(PEDIDO, identidade="extra#42"), INSTANTE)
    atual.confirmar_parte(PEDIDO.identidade, 0, "texto", 1, INSTANTE)
    assert repositorio.indices_confirmados("extra#42") == {0}


def test_pedido_legado_terminal_e_reconhecido_sem_criar_outro(repositorio: Any) -> None:
    repositorio.tabela.put_item(
        Item={
            "pk": "pedido#extra#42",
            "sk": "pedido",
            "identidade": "extra#42",
            "origem": "extra",
            "chat_id": 123456789,
            "estado": "enviado",
            "frase_reservada": "f1",
            "criado_em": INSTANTE.isoformat(),
        }
    )
    atual = RepositorioDePedidosDynamo(repositorio.tabela, bot_legado="bot-ficticio")

    assert not atual.criar_se_ausente(PEDIDO, INSTANTE)
    recuperado = atual.obter(PEDIDO.identidade)
    assert recuperado is not None
    assert recuperado.estado is EstadoDoPedido.ENVIADO
    outro = replace(PEDIDO, identidade="extra#outro-bot#42")
    assert atual.criar_se_ausente(outro, INSTANTE)
    recuperado = atual.obter(outro.identidade)
    assert recuperado is not None
    assert recuperado.estado is EstadoDoPedido.PENDENTE


def test_avanco_pela_versao_anterior_prevalece_sobre_estado_atual(repositorio: Any) -> None:
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)
    repositorio.salvar(PEDIDO.reservar("f1"))
    repositorio.tabela.update_item(
        Key={"pk": "pedido#" + PEDIDO.identidade, "sk": "pedido"},
        UpdateExpression="SET estado = :e",
        ExpressionAttributeValues={":e": "enviado"},
    )

    assert repositorio.obter(PEDIDO.identidade).estado is EstadoDoPedido.ENVIADO
    assert repositorio.buscar_vencidos(INSTANTE) == []


def test_finalizar_tentativa_preserva_identidade_versao_e_correlacao(repositorio: Any) -> None:
    atual = RepositorioDePedidosDynamo(repositorio.tabela, versao="sha-ficticio")
    sequencial = atual.registrar_tentativa(PEDIDO.identidade, "iniciada", None, INSTANTE)
    antes = atual.listar_tentativas(PEDIDO.identidade)[0]
    atual.finalizar_tentativa(PEDIDO.identidade, sequencial, "erro", "token=SEGREDO", INSTANTE)
    depois = atual.listar_tentativas(PEDIDO.identidade)[0]

    assert depois["identidade"] == antes["identidade"]
    assert depois["correlacao"] == antes["correlacao"]
    assert depois["versao"] == "sha-ficticio"
    assert depois["erro"] == "erro de integração"
    assert depois["finalizada_em"] == "2026-09-07T12:00:00.000000+00:00"


def test_consultas_percorrem_todas_as_paginas(
    repositorio: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = repositorio.tabela.query

    def pagina_pequena(**argumentos: Any) -> Any:
        return query(**argumentos, Limit=1)

    monkeypatch.setattr(repositorio.tabela, "query", pagina_pequena)
    for indice in range(3):
        repositorio.criar_se_ausente(replace(PEDIDO, identidade=f"pedido-{indice}"), INSTANTE)
        repositorio.confirmar_parte(PEDIDO.identidade, indice, "texto", 900 + indice, INSTANTE)
        repositorio.registrar_tentativa(PEDIDO.identidade, "erro", None, INSTANTE)

    assert len(repositorio.buscar_vencidos(INSTANTE)) == 3
    assert repositorio.indices_confirmados(PEDIDO.identidade) == {0, 1, 2}
    assert len(repositorio.listar_tentativas(PEDIDO.identidade)) == 3


def test_instante_sem_fuso_e_rejeitado_antes_de_persistir(repositorio: Any) -> None:
    with pytest.raises(ValueError, match="fuso"):
        repositorio.criar_se_ausente(PEDIDO, datetime(2026, 9, 7, 12))
    assert repositorio.obter(PEDIDO.identidade) is None


def test_adocao_dos_legados_e_aditiva_paginada_e_reexecutavel(
    repositorio: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    for identidade, estado in (("antigo", "pendente"), ("terminado", "enviado")):
        repositorio.tabela.put_item(
            Item={
                "pk": f"pedido#{identidade}",
                "sk": "pedido",
                "identidade": identidade,
                "origem": "extra",
                "chat_id": 123456789,
                "estado": estado,
                "criado_em": INSTANTE.isoformat(),
            }
        )
    repositorio.confirmar_parte("antigo", 0, "histórico preservado", 1, INSTANTE)
    scan = repositorio.tabela.scan

    def pagina_pequena(**argumentos: Any) -> Any:
        return scan(**argumentos, Limit=1)

    monkeypatch.setattr(repositorio.tabela, "scan", pagina_pequena)

    assert indexar_pedidos_legados(repositorio.tabela) == 1
    assert indexar_pedidos_legados(repositorio.tabela) == 0
    assert [p.identidade for p in repositorio.buscar_vencidos(INSTANTE)] == ["antigo"]
    assert repositorio.indices_confirmados("antigo") == {0}


# --- lease e concorrência (ticket 09) -----------------------------------------


def test_um_sequencial_mais_novo_sempre_assume_o_lease(repositorio: Any) -> None:
    # O sequencial vem de um contador atômico: quando este executor o obteve,
    # nenhum outro ainda tinha um valor maior. A reivindicação nunca bloqueia.
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)

    repositorio.assumir_lease(PEDIDO.identidade, 1, INSTANTE, timedelta(minutes=5))
    repositorio.assumir_lease(PEDIDO.identidade, 2, INSTANTE, timedelta(minutes=5))


def test_reassumir_o_proprio_lease_e_idempotente(repositorio: Any) -> None:
    # Regressão (achado do code-review): um retry automático do SDK sobre a
    # mesma tentativa, depois que a primeira chamada já teve sucesso no
    # servidor, não pode ser recusado como se um outro executor tivesse
    # assumido o lease — é a mesma tentativa reafirmando o que já é seu.
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)

    repositorio.assumir_lease(PEDIDO.identidade, 1, INSTANTE, timedelta(minutes=5))
    repositorio.assumir_lease(PEDIDO.identidade, 1, INSTANTE, timedelta(minutes=5))


def test_um_sequencial_mais_antigo_nao_assume_lease_vigente(repositorio: Any) -> None:
    # O mesmo evento entregue duas vezes pela invocação assíncrona da Lambda não
    # depende do reconciliador para gerar esta corrida.
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)
    repositorio.assumir_lease(PEDIDO.identidade, 2, INSTANTE, timedelta(minutes=5))

    with pytest.raises(ConflitoDeConcorrencia):
        repositorio.assumir_lease(PEDIDO.identidade, 1, INSTANTE, timedelta(minutes=5))


def test_lease_vencido_pode_ser_assumido_por_qualquer_sequencial(repositorio: Any) -> None:
    # Sem isto, uma execução que travou sem nunca renovar o lease bloquearia o
    # pedido para sempre — o ticket exige que seja reconciliável.
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)
    repositorio.assumir_lease(PEDIDO.identidade, 5, INSTANTE, timedelta(minutes=5))
    depois_de_vencer = INSTANTE + timedelta(minutes=6)

    repositorio.assumir_lease(PEDIDO.identidade, 1, depois_de_vencer, timedelta(minutes=5))


def test_salvar_recusa_um_sequencial_que_ja_nao_e_dono_do_lease(repositorio: Any) -> None:
    # É o que impede um executor superado de confirmar o estado final do
    # pedido — mesmo que ele só descubra isso ao tentar gravar (AC03).
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)
    repositorio.assumir_lease(PEDIDO.identidade, 1, INSTANTE, timedelta(minutes=5))
    repositorio.assumir_lease(PEDIDO.identidade, 2, INSTANTE, timedelta(minutes=5))

    with pytest.raises(ConflitoDeConcorrencia):
        repositorio.salvar(PEDIDO.reservar("f1"), sequencial=1)

    repositorio.salvar(PEDIDO.reservar("f1"), sequencial=2)
    assert repositorio.obter(PEDIDO.identidade).frase_reservada == "f1"


def test_confirmar_parte_recusa_um_sequencial_que_ja_nao_e_dono_do_lease(repositorio: Any) -> None:
    # "Confirmar entrega" é literalmente isto: sem a condição, um executor
    # superado poderia gravar uma confirmação depois que outro já concluiu.
    repositorio.criar_se_ausente(PEDIDO, INSTANTE)
    repositorio.assumir_lease(PEDIDO.identidade, 1, INSTANTE, timedelta(minutes=5))
    repositorio.assumir_lease(PEDIDO.identidade, 2, INSTANTE, timedelta(minutes=5))

    with pytest.raises(ConflitoDeConcorrencia):
        repositorio.confirmar_parte(PEDIDO.identidade, 0, "texto", 901, INSTANTE, sequencial=1)

    repositorio.confirmar_parte(PEDIDO.identidade, 0, "texto", 901, INSTANTE, sequencial=2)
    assert repositorio.indices_confirmados(PEDIDO.identidade) == {0}
