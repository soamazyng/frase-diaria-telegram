"""O token do Notion vai no cabeçalho `Authorization`, nunca na URL.

Ainda assim, qualquer exceção precisa ser sanitizada: o padrão é o mesmo do
Telegram (`telegram/canal.py`) — nunca repetir o cabeçalho de autenticação nem
o corpo bruto da resposta.
"""

import http.client
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


def test_busca_filhos_aceita_o_id_com_titulo_da_url_colada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Copiar o link de uma página do Notion traz o título como prefixo do id
    # (`Titulo-Da-Colecao-<32hex>`); a API só aceita o id puro. Achado ao
    # validar o acesso de produção pela primeira vez (HTTP 400).
    capturado: dict[str, Any] = {}
    id_puro = "8f3a1b2c4d5e6f708192a3b4c5d6e7f8"

    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        capturado["url"] = requisicao.full_url
        return _resposta({"results": [], "has_more": False})

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)

    ClienteNotionHttp(token=TOKEN).buscar_filhos(f"Titulo-Da-Colecao-{id_puro}")

    assert f"{id_puro}/children" in capturado["url"]
    assert "Titulo-Da-Colecao" not in capturado["url"]


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


def test_falha_de_rede_vira_erro_do_notion_sem_vazar_o_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        raise urllib.error.URLError(f"falha ao conectar em {requisicao.full_url}")

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)

    with pytest.raises(ErroDoNotion) as capturado:
        ClienteNotionHttp(token=TOKEN).buscar_filhos("pagina-1")

    assert TOKEN not in str(capturado.value)


def test_conexao_encerrada_sem_resposta_tambem_vira_erro_do_notion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regressão: mesma falha de transporte já corrigida em telegram/canal.py.

    `urllib` nem sempre embrulha em `URLError` — `RemoteDisconnected` foi
    observada em produção do lado do Telegram. Sem este tratamento aqui
    também, a mesma classe de falha do lado do Notion escaparia como exceção
    crua, pulando o fallback para o snapshot em cache (AC09).
    """

    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        raise http.client.RemoteDisconnected("conexão encerrada")

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


def test_normalizar_id_aceita_uuid_com_tracos_e_titulo(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado: dict[str, Any] = {}
    uuid_com_tracos = "8f3a1b2c-4d5e-6f70-8192-a3b4c5d6e7f8"

    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        capturado["url"] = requisicao.full_url
        return _resposta({"results": [], "has_more": False})

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)

    ClienteNotionHttp(token=TOKEN).buscar_filhos(f"Outro-Titulo-{uuid_com_tracos}")

    assert f"{uuid_com_tracos}/children" in capturado["url"]


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
