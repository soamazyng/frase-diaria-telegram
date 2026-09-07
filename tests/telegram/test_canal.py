"""O token do bot vai na URL da Bot API.

Isso significa que qualquer exceção que carregue a URL vaza o token para os logs
— e a spec exige sanitizar tokens. Estes testes prendem esse comportamento.
"""

import json
import urllib.error
from email.message import Message
from typing import Any

import pytest

from frase_diaria.telegram.canal import (
    MESSAGE_ID_DESCONHECIDO,
    ErroDoTelegram,
    TelegramHttp,
)

TOKEN = "123456:TOKEN-SUPER-SECRETO"


def test_envia_texto_para_a_conversa(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado: dict[str, Any] = {}

    class RespostaFalsa:
        def read(self) -> bytes:
            return json.dumps({"ok": True, "result": {"message_id": 12}}).encode()

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_):  # type: ignore[no-untyped-def]
            return False

    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        capturado["url"] = requisicao.full_url
        capturado["corpo"] = json.loads(requisicao.data)
        return RespostaFalsa()

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)

    message_id = TelegramHttp(token=TOKEN).enviar_texto(8340090374, "olá")

    assert message_id == 12
    assert capturado["corpo"]["chat_id"] == 8340090374
    assert capturado["corpo"]["text"] == "olá"
    assert "sendMessage" in capturado["url"]


def test_erro_http_nao_vaza_o_token_na_excecao(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        raise urllib.error.HTTPError(
            url=requisicao.full_url, code=401, msg="Unauthorized", hdrs=Message(), fp=None
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)

    with pytest.raises(ErroDoTelegram) as capturado:
        TelegramHttp(token=TOKEN).enviar_texto(8340090374, "olá")

    mensagem = str(capturado.value)
    assert TOKEN not in mensagem
    assert "TOKEN-SUPER-SECRETO" not in mensagem
    assert "401" in mensagem


def test_erro_de_rede_nao_vaza_o_token(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen_falso(requisicao, timeout=None):  # type: ignore[no-untyped-def]
        raise urllib.error.URLError(f"falha ao conectar em {requisicao.full_url}")

    monkeypatch.setattr("urllib.request.urlopen", urlopen_falso)

    with pytest.raises(ErroDoTelegram) as capturado:
        TelegramHttp(token=TOKEN).enviar_texto(8340090374, "olá")

    assert "TOKEN-SUPER-SECRETO" not in str(capturado.value)


def test_resposta_com_ok_falso_vira_erro(monkeypatch: pytest.MonkeyPatch) -> None:
    class RespostaFalsa:
        def read(self) -> bytes:
            return json.dumps({"ok": False, "description": "chat not found"}).encode()

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_):  # type: ignore[no-untyped-def]
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: RespostaFalsa())

    with pytest.raises(ErroDoTelegram, match="chat not found"):
        TelegramHttp(token=TOKEN).enviar_texto(8340090374, "olá")


def test_resposta_sem_message_id_conta_como_entregue(monkeypatch: pytest.MonkeyPatch) -> None:
    """`ok: true` significa que a mensagem foi entregue.

    Tratar a ausência de message_id como falha faria o pedido registrar como não
    enviada uma frase que a usuária recebeu — e, sendo a primeira parte, liberaria
    a reserva. Melhor perder o identificador do que negar a entrega.
    """

    class SemMessageId:
        def read(self) -> bytes:
            return json.dumps({"ok": True, "result": {}}).encode()

        def __enter__(self) -> "SemMessageId":
            return self

        def __exit__(self, *_: Any) -> None:
            return None

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: SemMessageId())

    assert TelegramHttp(token=TOKEN).enviar_texto(8340090374, "olá") == MESSAGE_ID_DESCONHECIDO


def test_corpo_ilegivel_da_bot_api_vira_erro_do_telegram(monkeypatch: pytest.MonkeyPatch) -> None:
    # Sem isto o ValueError escapa e o pedido fica preso, sem tentativa registrada.
    class Ilegivel:
        def read(self) -> bytes:
            return b"<html>gateway timeout</html>"

        def __enter__(self) -> "Ilegivel":
            return self

        def __exit__(self, *_: Any) -> None:
            return None

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Ilegivel())

    with pytest.raises(ErroDoTelegram, match="resposta ilegível"):
        TelegramHttp(token=TOKEN).enviar_texto(8340090374, "olá")
