import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

BASE = "https://api.telegram.org"


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

    def enviar_texto(self, chat_id: int, texto: str) -> None:
        corpo = json.dumps({"chat_id": chat_id, "text": texto}).encode("utf-8")
        requisicao = urllib.request.Request(
            f"{BASE}/bot{self.token}/sendMessage",
            data=corpo,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(requisicao, timeout=self.timeout_s) as resposta:
                carga = json.loads(resposta.read())
        except urllib.error.HTTPError as erro:
            # A URL do erro contém o token: reporta só o código.
            raise ErroDoTelegram(f"Bot API respondeu HTTP {erro.code}") from None
        except urllib.error.URLError:
            # A mensagem original pode embutir a URL: descarta-se o encadeamento.
            raise ErroDoTelegram("falha de rede ao chamar a Bot API") from None

        if not carga.get("ok"):
            raise ErroDoTelegram(f"Bot API recusou: {carga.get('description', 'sem descrição')}")
