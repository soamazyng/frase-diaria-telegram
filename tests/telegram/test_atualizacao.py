"""Leitura do Update do Telegram.

Um update que não é uma mensagem de conversa é irrelevante para este bot e deve
ser reconhecido e ignorado — não é erro, não gera pedido, e o Telegram precisa
receber sucesso para parar de reentregar.
"""

from typing import Any

from frase_diaria.dominio.comando import Comando
from frase_diaria.telegram.atualizacao import interpretar


def _mensagem(
    texto: str = "/start", chat_id: int = 111111, tipo: str = "private"
) -> dict[str, Any]:
    return {
        "update_id": 10001,
        "message": {
            "message_id": 7,
            "chat": {"id": chat_id, "type": tipo},
            "text": texto,
        },
    }


def test_le_update_id_conversa_e_comando() -> None:
    atualizacao = interpretar(_mensagem("/start"))

    assert atualizacao is not None
    assert atualizacao.update_id == 10001
    assert atualizacao.conversa.chat_id == 111111
    assert atualizacao.conversa.tipo == "private"
    assert atualizacao.comando is Comando.START


def test_reconhece_frase_e_status() -> None:
    assert interpretar(_mensagem("/frase")).comando is Comando.FRASE  # type: ignore[union-attr]
    assert interpretar(_mensagem("/status")).comando is Comando.STATUS  # type: ignore[union-attr]


def test_aceita_comando_com_mencao_ao_bot() -> None:
    # O Telegram entrega "/frase@meu_bot" quando há menção explícita.
    assert interpretar(_mensagem("/frase@frase_diaria_bot")).comando is Comando.FRASE  # type: ignore[union-attr]


def test_texto_que_nao_e_comando_vira_desconhecido() -> None:
    assert interpretar(_mensagem("bom dia")).comando is Comando.DESCONHECIDO  # type: ignore[union-attr]


def test_comando_inexistente_vira_desconhecido() -> None:
    assert interpretar(_mensagem("/inventado")).comando is Comando.DESCONHECIDO  # type: ignore[union-attr]


def test_preserva_a_conversa_mesmo_quando_nao_e_privada() -> None:
    # A recusa é decisão da política de acesso, não do parser: ele apenas relata.
    atualizacao = interpretar(_mensagem("/frase", tipo="group"))

    assert atualizacao is not None
    assert atualizacao.conversa.tipo == "group"


def test_update_sem_mensagem_e_irrelevante() -> None:
    assert interpretar({"update_id": 5, "poll": {"id": "1"}}) is None


def test_update_sem_chat_e_irrelevante() -> None:
    assert interpretar({"update_id": 5, "message": {"text": "oi"}}) is None


def test_update_sem_update_id_e_irrelevante() -> None:
    sem_id = {"message": {"chat": {"id": 1, "type": "private"}, "text": "/frase"}}

    assert interpretar(sem_id) is None


def test_mensagem_sem_texto_e_relevante_mas_desconhecida() -> None:
    # Uma foto enviada na conversa autorizada merece a ajuda curta, não silêncio.
    sem_texto = {"update_id": 9, "message": {"chat": {"id": 111111, "type": "private"}}}

    atualizacao = interpretar(sem_texto)

    assert atualizacao is not None
    assert atualizacao.comando is Comando.DESCONHECIDO


def test_corpo_vazio_e_irrelevante() -> None:
    assert interpretar({}) is None
