"""O token do Notion vai no cabeçalho `Authorization`, nunca na URL.

Ainda assim, qualquer exceção precisa ser sanitizada: o padrão é o mesmo do
Telegram (`telegram/canal.py`) — nunca repetir o cabeçalho de autenticação nem
o corpo bruto da resposta.
"""

import json
import urllib.error
from email.message import Message
from typing import Any

import pytest

from frase_diaria.notion.cliente import AcessoNegado, ClienteNotionHttp, ErroDoNotion

TOKEN = "secret_TOKEN-SUPER-SECRETO"


def _resposta(corpo: dict[str, Any]) -> Any:
    class RespostaFalsa:
        def read(self) -> bytes:
            return json.dumps(corpo).encode()

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_):  # type: ignore[no-untyped-def]
            return False

    return RespostaFalsa()


def test_busca_filhos_envia_o_token_no_cabecalho(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado: dict[str, Any] = {}

    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        capturado["url"] = requisicao.full_url
        capturado["autorizacao"] = requisicao.get_header("Authorization")
        return _resposta({"results": [{"id": "b1", "type": "paragraph"}], "has_more": False})

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)

    filhos = ClienteNotionHttp(token=TOKEN).buscar_filhos("pagina-1")

    assert filhos == ({"id": "b1", "type": "paragraph"},)
    assert capturado["autorizacao"] == f"Bearer {TOKEN}"
    assert "pagina-1/children" in capturado["url"]


def test_busca_filhos_percorre_toda_a_paginacao(monkeypatch: pytest.MonkeyPatch) -> None:
    paginas = [
        {"results": [{"id": "b1", "type": "paragraph"}], "has_more": True, "next_cursor": "c1"},
        {"results": [{"id": "b2", "type": "paragraph"}], "has_more": False},
    ]
    chamadas: list[str | None] = []

    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        chamadas.append("c1" if "start_cursor=c1" in requisicao.full_url else None)
        return _resposta(paginas[len(chamadas) - 1])

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)

    filhos = ClienteNotionHttp(token=TOKEN).buscar_filhos("pagina-1")

    assert [f["id"] for f in filhos] == ["b1", "b2"]
    assert chamadas == [None, "c1"]


def test_paginacao_incompleta_nao_devolve_resultado_parcial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Erro na segunda página não pode virar uma lista truncada de filhos: quem
    # chama precisa saber que a leitura não terminou (AC08).
    chamadas = {"n": 0}

    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            return _resposta({"results": [{"id": "b1"}], "has_more": True, "next_cursor": "c1"})
        raise urllib.error.HTTPError(
            url=requisicao.full_url, code=504, msg="Gateway Timeout", hdrs=Message(), fp=None
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)

    with pytest.raises(ErroDoNotion):
        ClienteNotionHttp(token=TOKEN).buscar_filhos("pagina-1")


def test_erro_http_nao_vaza_o_token_na_excecao(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        raise urllib.error.HTTPError(
            url=requisicao.full_url, code=401, msg="Unauthorized", hdrs=Message(), fp=None
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)

    with pytest.raises(ErroDoNotion) as capturado:
        ClienteNotionHttp(token=TOKEN).buscar_filhos("pagina-1")

    assert TOKEN not in str(capturado.value)


def test_acesso_negado_e_um_erro_distinguivel(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        raise urllib.error.HTTPError(
            url=requisicao.full_url, code=403, msg="Forbidden", hdrs=Message(), fp=None
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)

    with pytest.raises(AcessoNegado):
        ClienteNotionHttp(token=TOKEN).buscar_filhos("pagina-1")


def test_busca_comentarios_devolve_none_quando_acesso_e_negado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Discussões nativas são um recurso à parte: perder acesso a elas não pode
    # invalidar a coleção inteira, só virar diagnóstico (spec, 4.2).
    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        raise urllib.error.HTTPError(
            url=requisicao.full_url, code=403, msg="Forbidden", hdrs=Message(), fp=None
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)

    assert ClienteNotionHttp(token=TOKEN).buscar_comentarios("bloco-1") is None


def test_busca_comentarios_sem_negacao_devolve_os_itens(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        assert "block_id=bloco-1" in requisicao.full_url
        return _resposta({"results": [{"id": "com-1"}], "has_more": False})

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)

    comentarios = ClienteNotionHttp(token=TOKEN).buscar_comentarios("bloco-1")

    assert comentarios == ({"id": "com-1"},)


def test_rate_limit_espera_e_tenta_de_novo(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas = {"n": 0}
    esperas: list[float] = []

    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            cabecalhos = Message()
            cabecalhos["Retry-After"] = "0"
            raise urllib.error.HTTPError(
                url=requisicao.full_url, code=429, msg="Too Many Requests", hdrs=cabecalhos, fp=None
            )
        return _resposta({"results": [{"id": "b1"}], "has_more": False})

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)
    monkeypatch.setattr("time.sleep", lambda segundos: esperas.append(segundos))

    filhos = ClienteNotionHttp(token=TOKEN).buscar_filhos("pagina-1")

    assert filhos == ({"id": "b1"},)
    assert esperas == [0.0]


def test_has_more_sem_next_cursor_nao_entra_em_loop_infinito(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Resposta malformada (achado do code-review): sem isto, a mesma página
    # seria repedida para sempre, travando a Lambda até o timeout.
    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        return _resposta({"results": [{"id": "b1"}], "has_more": True})

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)

    with pytest.raises(ErroDoNotion, match="has_more"):
        ClienteNotionHttp(token=TOKEN).buscar_filhos("pagina-1")


def test_resposta_ilegivel_nao_propaga_o_corpo_bruto(monkeypatch: pytest.MonkeyPatch) -> None:
    class RespostaIlegivel:
        def read(self) -> bytes:
            return b"<html>nao e json</html>"

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_):  # type: ignore[no-untyped-def]
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: RespostaIlegivel())

    with pytest.raises(ErroDoNotion, match="ilegível"):
        ClienteNotionHttp(token=TOKEN).buscar_filhos("pagina-1")
