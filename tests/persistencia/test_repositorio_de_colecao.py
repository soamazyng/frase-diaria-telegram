"""O snapshot ativo da coleção precisa sobreviver a reinícios da aplicação.

Cabe em um único item porque a coleção é pessoal e pequena (dezenas de
frases) — o mesmo raciocínio já aplicado ao ciclo em `persistencia/ciclos.py`.
"""

from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from moto import mock_aws

from frase_diaria.dominio.colecao import ColecaoValida, Diagnostico, FrasePreservada
from frase_diaria.dominio.conteudo import Bloco, Trecho
from frase_diaria.persistencia.colecao import RepositorioDeColecaoDynamo

TABELA = "frase-diaria-estado-teste"
INSTANTE = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


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
        yield RepositorioDeColecaoDynamo(tabela=dynamo.Table(TABELA))


def _frase(identidade: str, texto: str) -> FrasePreservada:
    return FrasePreservada(
        identidade=identidade,
        blocos=(Bloco(tipo="numbered_list_item", trechos=(Trecho(texto=texto),)),),
    )


def test_sem_snapshot_gravado_devolve_none(repositorio: Any) -> None:
    assert repositorio.carregar_ativa() is None


def test_snapshot_gravado_sobrevive_a_um_reinicio(repositorio: Any) -> None:
    colecao = ColecaoValida(itens=(_frase("b1", "primeira"), _frase("b2", "segunda")))

    repositorio.substituir(colecao, INSTANTE)
    persistido = repositorio.carregar_ativa()

    assert persistido is not None
    assert persistido.instante == INSTANTE
    assert persistido.identificador
    assert [f.identidade for f in persistido.colecao.itens] == ["b1", "b2"]
    assert persistido.colecao.itens[0].blocos[0].trechos[0].texto == "primeira"


def test_substituicao_mais_antiga_nao_sobrescreve_a_mais_recente(repositorio: Any) -> None:
    # Regressão (achado do code-review): duas sincronizações concorrentes
    # podem terminar fora de ordem. Se a mais antiga vencer por chegar por
    # último, ela ressuscitaria momentaneamente uma frase já excluída na mais
    # recente — o oposto do que "nunca ressuscita frases excluídas" promete.
    recente = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    antiga = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)

    repositorio.substituir(ColecaoValida(itens=(_frase("b2", "nova"),)), recente)
    repositorio.substituir(ColecaoValida(itens=(_frase("b1", "velha"),)), antiga)

    persistido = repositorio.carregar_ativa()
    assert persistido is not None
    assert [f.identidade for f in persistido.colecao.itens] == ["b2"]
    assert persistido.instante == recente


def test_cada_substituicao_ganha_um_identificador_novo(repositorio: Any) -> None:
    repositorio.substituir(ColecaoValida(itens=(_frase("b1", "primeira"),)), INSTANTE)
    primeiro = repositorio.carregar_ativa()
    assert primeiro is not None

    depois = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    repositorio.substituir(ColecaoValida(itens=(_frase("b1", "primeira"),)), depois)
    segundo = repositorio.carregar_ativa()
    assert segundo is not None

    assert primeiro.identificador != segundo.identificador


def test_preserva_rich_text_blocos_e_discussoes(repositorio: Any) -> None:
    frase = FrasePreservada(
        identidade="b1",
        blocos=(
            Bloco(
                tipo="numbered_list_item",
                trechos=(Trecho(texto="negrito", negrito=True, link="https://exemplo.com"),),
            ),
            Bloco(tipo="paragraph", trechos=(Trecho(texto="descendente"),)),
        ),
        discussoes=("um comentário",),
    )

    repositorio.substituir(ColecaoValida(itens=(frase,)), INSTANTE)
    persistido = repositorio.carregar_ativa()

    assert persistido is not None
    recuperada = persistido.colecao.itens[0]
    assert recuperada.discussoes == ("um comentário",)
    assert recuperada.blocos[0].trechos[0].negrito is True
    assert recuperada.blocos[0].trechos[0].link == "https://exemplo.com"
    assert recuperada.blocos[1].tipo == "paragraph"


def test_substituir_por_colecao_vazia_nao_ressuscita_frases_antigas(repositorio: Any) -> None:
    # Leitura completa sem frases substitui a coleção por um snapshot vazio;
    # não pode continuar servindo as frases da versão anterior (AC09).
    repositorio.substituir(ColecaoValida(itens=(_frase("b1", "vai sumir"),)), INSTANTE)

    repositorio.substituir(ColecaoValida(itens=()), INSTANTE)
    persistido = repositorio.carregar_ativa()

    assert persistido is not None
    assert persistido.colecao.itens == ()


def test_diagnosticos_sobrevivem_a_um_reinicio(repositorio: Any) -> None:
    # Regressão (achado do code-review): sem persistir os diagnósticos, um
    # acesso negado a discussões ou um conteúdo solto vira invisível assim que
    # a Lambda encerra o container — mesmo o domínio dizendo que "precisam
    # ficar visíveis" (spec, 4.2).
    diagnostico = Diagnostico(categoria="acesso_negado", descricao="sem acesso ao bloco b1")
    colecao = ColecaoValida(itens=(_frase("b1", "texto"),), diagnosticos=(diagnostico,))

    repositorio.substituir(colecao, INSTANTE)
    persistido = repositorio.carregar_ativa()

    assert persistido is not None
    assert persistido.colecao.diagnosticos == (diagnostico,)


def test_substituir_troca_completamente_a_lista_de_frases(repositorio: Any) -> None:
    # Uma frase que saiu da coleção não pode continuar aparecendo no cache
    # depois de uma sincronização bem-sucedida que não a trouxe mais.
    repositorio.substituir(ColecaoValida(itens=(_frase("b1", "antiga"),)), INSTANTE)

    depois = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    repositorio.substituir(ColecaoValida(itens=(_frase("b2", "nova"),)), depois)
    persistido = repositorio.carregar_ativa()

    assert persistido is not None
    assert [f.identidade for f in persistido.colecao.itens] == ["b2"]
    assert persistido.instante == depois
