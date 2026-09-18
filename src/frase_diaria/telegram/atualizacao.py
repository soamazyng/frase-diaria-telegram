from typing import Any

from frase_diaria.dominio.atualizacao import Atualizacao
from frase_diaria.dominio.autorizacao import Conversa
from frase_diaria.dominio.comando import Comando

__all__ = ["Atualizacao", "interpretar"]


def interpretar(corpo: dict[str, Any]) -> Atualizacao | None:
    """Converte o corpo do webhook em Atualizacao, ou None se for irrelevante.

    Irrelevante significa que não é uma mensagem de conversa: enquete, resultado
    de inline query, corpo vazio. Nada disso é erro — o Telegram recebe sucesso e
    para de reentregar.

    A validação de acesso NÃO acontece aqui: o parser relata a conversa como ela
    veio, e a decisão de aceitar é da política de acesso.
    """
    update_id = corpo.get("update_id")
    if not isinstance(update_id, int):
        return None

    mensagem = corpo.get("message")
    if not isinstance(mensagem, dict):
        return None

    chat = mensagem.get("chat")
    if not isinstance(chat, dict):
        return None

    chat_id = chat.get("id")
    tipo = chat.get("type")
    if not isinstance(chat_id, int) or not isinstance(tipo, str):
        return None

    texto = mensagem.get("text")
    return Atualizacao(
        update_id=update_id,
        conversa=Conversa(chat_id=chat_id, tipo=tipo),
        comando=Comando.de_texto(texto if isinstance(texto, str) else None),
    )
