import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field

_log = logging.getLogger(__name__)

BASE = "https://api.telegram.org"

# A Bot API respondeu ok mas não devolveu identificador. A mensagem foi entregue;
# só não há como referenciá-la depois.
MESSAGE_ID_DESCONHECIDO = 0


class ErroDoTelegram(RuntimeError):
    """Falha ao falar com a Bot API, já sanitizada.

    Nunca carrega a URL da chamada: o token do bot faz parte dela.
    """


@dataclass(frozen=True)
class TelegramHttp:
    """Cliente mínimo da Bot API sobre a biblioteca padrão.

    Usa `urllib` de propósito: evita uma dependência a mais no artefato da Lambda
    para o punhado de chamadas que este bot faz.
    """

    token: str = field(repr=False)
    timeout_s: float = 10.0

    def enviar_texto(self, chat_id: int, texto: str) -> int:
        """Envia uma mensagem e devolve o message_id atribuído pelo Telegram.

        O message_id é o que torna a entrega verificável depois: sem ele, o
        histórico registraria "enviei" sem poder apontar o que foi enviado.
        """
        corpo = json.dumps({"chat_id": chat_id, "text": texto, "parse_mode": "HTML"}).encode(
            "utf-8"
        )
        requisicao = urllib.request.Request(
            f"{BASE}/bot{self.token}/sendMessage",
            data=corpo,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(requisicao, timeout=self.timeout_s) as resposta:
                bruto = resposta.read()
        except urllib.error.HTTPError as erro:
            # A URL do erro contém o token: reporta só o código.
            raise ErroDoTelegram(f"Bot API respondeu HTTP {erro.code}") from None
        except urllib.error.URLError:
            # A mensagem original pode embutir a URL: descarta-se o encadeamento.
            raise ErroDoTelegram("falha de rede ao chamar a Bot API") from None

        try:
            carga = json.loads(bruto)
        except ValueError:
            # Um proxy pode devolver HTML com status 200. Sem este tratamento o
            # ValueError escaparia e o pedido ficaria preso, sem tentativa.
            raise ErroDoTelegram("Bot API devolveu resposta ilegível") from None

        if not carga.get("ok"):
            raise ErroDoTelegram(f"Bot API recusou: {carga.get('description', 'sem descrição')}")

        message_id = carga.get("result", {}).get("message_id")
        if not isinstance(message_id, int):
            # A mensagem foi entregue: negar isso liberaria a reserva de uma
            # frase que a usuária já recebeu.
            _log.warning("Bot API respondeu ok sem message_id")
            return MESSAGE_ID_DESCONHECIDO
        return message_id
