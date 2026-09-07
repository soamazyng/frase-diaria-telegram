"""A versão ativa é o que o AC21 compara com o SHA publicado.

Se o nome da variável divergir do que o pipeline injeta, `/health` passa a relatar
"desenvolvimento" em produção e o AC21 compara o SHA contra um literal que nunca
casa — com a suíte inteira verde. Estes testes prendem o nome da variável.
"""

import pytest
from fastapi.testclient import TestClient

from frase_diaria.infraestrutura.configuracao import (
    VARIAVEL_DE_VERSAO,
    VERSAO_EM_DESENVOLVIMENTO,
    versao_da_aplicacao,
)
from frase_diaria.infraestrutura.http.aplicacao_web import criar_aplicacao


def test_a_variavel_de_ambiente_se_chama_exatamente_o_que_o_pipeline_injeta() -> None:
    assert VARIAVEL_DE_VERSAO == "VERSAO_DA_APLICACAO"


def test_usa_a_versao_do_ambiente_quando_definida(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(VARIAVEL_DE_VERSAO, "abc1234")

    assert versao_da_aplicacao() == "abc1234"


def test_cai_para_desenvolvimento_quando_a_variavel_esta_ausente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(VARIAVEL_DE_VERSAO, raising=False)

    assert versao_da_aplicacao() == VERSAO_EM_DESENVOLVIMENTO


def test_cai_para_desenvolvimento_quando_a_variavel_esta_vazia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(VARIAVEL_DE_VERSAO, "")

    assert versao_da_aplicacao() == VERSAO_EM_DESENVOLVIMENTO


def test_health_sem_versao_explicita_relata_a_versao_do_ambiente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(VARIAVEL_DE_VERSAO, "sha-do-commit-publicado")
    cliente = TestClient(criar_aplicacao())

    assert cliente.get("/health").json()["versao"] == "sha-do-commit-publicado"
