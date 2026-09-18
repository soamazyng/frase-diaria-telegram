"""A versão ativa é o que o AC21 compara com o SHA publicado.

Se o nome da variável divergir do que o pipeline injeta, `/health` passa a relatar
"desenvolvimento" em produção e o AC21 compara o SHA contra um literal que nunca
casa — com a suíte inteira verde. Estes testes prendem o nome da variável.
"""

import pytest
from fastapi.testclient import TestClient

from frase_diaria.infraestrutura.composicao import (
    PARAMETRO_OPCIONAL_DO_BOT_LEGADO,
    _bot_legado,
    _destinatarios_autorizados,
    _parametro,
    segredos,
)
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


def test_identificador_auxiliar_do_bot_pode_faltar_no_ssm() -> None:
    guardados = {"telegram-bot-token": "123456:token"}

    assert _bot_legado(guardados) == "123456"


def test_segredos_le_apenas_os_parametros_exatos(monkeypatch: pytest.MonkeyPatch) -> None:
    class ParameterNotFound(Exception):
        pass

    class ClienteFalso:
        def __init__(self) -> None:
            self.nomes: list[str] = []
            self.exceptions = type("ErrosDoCliente", (), {"ParameterNotFound": ParameterNotFound})

        def get_parameter(self, **argumentos: object) -> dict[str, object]:
            nome = str(argumentos["Name"])
            self.nomes.append(nome)
            assert argumentos["WithDecryption"] is True
            if nome.endswith(PARAMETRO_OPCIONAL_DO_BOT_LEGADO):
                raise ParameterNotFound
            return {"Parameter": {"Value": f"valor-{nome.rsplit('/', 1)[-1]}"}}

    cliente = ClienteFalso()
    monkeypatch.setattr(
        "frase_diaria.infraestrutura.composicao.boto3.client",
        lambda servico: cliente,
    )
    _parametro.cache_clear()

    obrigatorios = ("telegram-bot-token", "telegram-chat-ids")
    guardados = segredos(*obrigatorios)

    assert set(guardados) == set(obrigatorios)
    assert cliente.nomes == [
        *(f"/frase-diaria/{nome}" for nome in obrigatorios),
        f"/frase-diaria/{PARAMETRO_OPCIONAL_DO_BOT_LEGADO}",
    ]
    _parametro.cache_clear()


def test_destinatarios_autorizados_le_lista_separada_por_virgula() -> None:
    guardados = {"telegram-chat-ids": "111111,222222"}

    assert _destinatarios_autorizados(guardados) == frozenset({111111, 222222})


def test_destinatarios_autorizados_tolera_espacos_ao_redor_de_cada_valor() -> None:
    guardados = {"telegram-chat-ids": " 111111 , 222222 "}

    assert _destinatarios_autorizados(guardados) == frozenset({111111, 222222})


def test_destinatarios_autorizados_aceita_um_unico_valor_sem_virgula() -> None:
    guardados = {"telegram-chat-ids": "111111"}

    assert _destinatarios_autorizados(guardados) == frozenset({111111})


@pytest.mark.parametrize("valor", ["", ",", "   ", " , , "])
def test_destinatarios_autorizados_falha_alto_em_vez_de_conjunto_vazio(valor: str) -> None:
    """Um conjunto vazio recusaria silenciosamente todo mundo, inclusive a usuária."""
    guardados = {"telegram-chat-ids": valor}

    with pytest.raises(ValueError, match="telegram-chat-ids"):
        _destinatarios_autorizados(guardados)
