import json

import pytest
from fastapi.testclient import TestClient

from frase_diaria.infraestrutura.http.aplicacao_web import criar_aplicacao

SEGREDOS = {
    "TELEGRAM_BOT_TOKEN": "token-secreto-do-bot",
    "TELEGRAM_CHAT_ID": "123456789",
    "NOTION_TOKEN": "token-secreto-do-notion",
    "WEBHOOK_SECRET": "segredo-do-webhook",
}


def test_health_responde_com_situacao_versao_e_instante() -> None:
    cliente = TestClient(criar_aplicacao(versao="abc1234"))

    resposta = cliente.get("/health")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["situacao"] == "ok"
    assert corpo["versao"] == "abc1234"
    assert corpo["instante"].endswith("+00:00")


def test_health_nao_expoe_segredos_nem_dados_pessoais(monkeypatch: pytest.MonkeyPatch) -> None:
    for variavel, valor in SEGREDOS.items():
        monkeypatch.setenv(variavel, valor)
    cliente = TestClient(criar_aplicacao(versao="abc1234"))

    corpo = json.dumps(cliente.get("/health").json())

    for valor in SEGREDOS.values():
        assert valor not in corpo


def test_health_expoe_apenas_os_campos_previstos() -> None:
    cliente = TestClient(criar_aplicacao(versao="abc1234"))

    assert set(cliente.get("/health").json()) == {"situacao", "versao", "instante"}
