"""Contrato HTTP do webhook.

O código de status é a única coisa que o Telegram observa, e ele governa a
reentrega: sucesso encerra, erro faz reentregar. Por isso "não autorizado" e
"irrelevante" respondem 200 — reentregar não mudaria nada — enquanto "não
consegui persistir" responde 500.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from frase_diaria.aplicacao.receber_comando import Desfecho
from frase_diaria.infraestrutura.http.aplicacao_web import criar_aplicacao

SEGREDO = "segredo-certo"
CABECALHO = "X-Telegram-Bot-Api-Secret-Token"


class CasoFalso:
    def __init__(self, desfecho: Desfecho) -> None:
        self.desfecho = desfecho
        self.chamadas: list[tuple[str | None, dict[str, Any]]] = []

    def executar(self, segredo: str | None, corpo: dict[str, Any]) -> Desfecho:
        self.chamadas.append((segredo, corpo))
        return self.desfecho


def _cliente(caso: CasoFalso) -> TestClient:
    return TestClient(criar_aplicacao(versao="teste", receber_comando=caso))


@pytest.mark.parametrize(
    ("desfecho", "esperado"),
    [
        (Desfecho.ACEITO, 200),
        (Desfecho.JA_CONHECIDO, 200),
        (Desfecho.IGNORADO, 200),
        (Desfecho.NAO_PERSISTIDO, 500),
    ],
)
def test_traduz_desfecho_em_codigo_http(desfecho: Desfecho, esperado: int) -> None:
    resposta = _cliente(CasoFalso(desfecho)).post(
        "/telegram/webhook", json={"update_id": 1}, headers={CABECALHO: SEGREDO}
    )

    assert resposta.status_code == esperado


def test_repassa_o_cabecalho_de_segredo_ao_caso_de_uso() -> None:
    caso = CasoFalso(Desfecho.ACEITO)

    _cliente(caso).post("/telegram/webhook", json={"update_id": 1}, headers={CABECALHO: SEGREDO})

    assert caso.chamadas[0][0] == SEGREDO


def test_ausencia_do_cabecalho_chega_como_none() -> None:
    caso = CasoFalso(Desfecho.IGNORADO)

    _cliente(caso).post("/telegram/webhook", json={"update_id": 1})

    assert caso.chamadas[0][0] is None


def test_corpo_invalido_responde_200_sem_chamar_o_caso_de_uso() -> None:
    # Um corpo que não é JSON nunca vai virar válido em uma reentrega.
    caso = CasoFalso(Desfecho.ACEITO)

    resposta = _cliente(caso).post(
        "/telegram/webhook", content=b"nao e json", headers={CABECALHO: SEGREDO}
    )

    assert resposta.status_code == 200
    assert caso.chamadas == []


def test_a_resposta_nao_revela_o_motivo_da_recusa() -> None:
    resposta = _cliente(CasoFalso(Desfecho.IGNORADO)).post(
        "/telegram/webhook", json={"update_id": 1}, headers={CABECALHO: "errado"}
    )

    corpo = resposta.text.lower()
    for pista in ("segredo", "chat", "autoriz", "privad"):
        assert pista not in corpo
