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

# Excesso de taxa e indisponibilidade do lado do Telegram: uma nova tentativa
# tem chance real de dar certo. Credencial inválida, bot bloqueado e outros 4xx
# não têm — retentar só adiaria o diagnóstico (spec, 4.5; AC13).
_CODIGOS_TRANSITORIOS = frozenset({429, 500, 502, 503, 504})


class ErroDoTelegram(RuntimeError):
    """Falha ao falar com a Bot API, já sanitizada.

    Nunca carrega a URL da chamada: o token do bot faz parte dela.

    `transitorio` diz se vale a pena retentar (AC13); `retry_after_s`, quando a
    Bot API o informou, é o quanto esperar antes de tentar de novo.
    """

    def __init__(
        self,
        mensagem: str,
        *,
        codigo_http: int | None = None,
        retry_after_s: float | None = None,
        transitorio: bool = False,
    ) -> None:
        super().__init__(mensagem)
        self.codigo_http = codigo_http
        self.retry_after_s = retry_after_s
        self.transitorio = transitorio


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
            raise ErroDoTelegram(
                f"Bot API respondeu HTTP {erro.code}",
                codigo_http=erro.code,
                retry_after_s=_retry_after_do_corpo_do_erro(erro),
                transitorio=erro.code in _CODIGOS_TRANSITORIOS,
            ) from None
        except urllib.error.URLError:
            # A mensagem original pode embutir a URL: descarta-se o encadeamento.
            # Uma falha de rede é, por natureza, transitória.
            raise ErroDoTelegram("falha de rede ao chamar a Bot API", transitorio=True) from None

        try:
            carga = json.loads(bruto)
        except ValueError:
            # Um proxy pode devolver HTML com status 200. Sem este tratamento o
            # ValueError escaparia e o pedido ficaria preso, sem tentativa. Uma
            # resposta ilegível também é, por natureza, transitória.
            raise ErroDoTelegram("Bot API devolveu resposta ilegível", transitorio=True) from None

        if not carga.get("ok"):
            codigo = carga.get("error_code")
            codigo = codigo if isinstance(codigo, int) else None
            raise ErroDoTelegram(
                f"Bot API recusou: {carga.get('description', 'sem descrição')}",
                codigo_http=codigo,
                retry_after_s=_retry_after_do_corpo(carga),
                transitorio=codigo in _CODIGOS_TRANSITORIOS,
            )

        message_id = carga.get("result", {}).get("message_id")
        if not isinstance(message_id, int):
            # A mensagem foi entregue: negar isso liberaria a reserva de uma
            # frase que a usuária já recebeu.
            _log.warning("Bot API respondeu ok sem message_id")
            return MESSAGE_ID_DESCONHECIDO
        return message_id


def _retry_after_do_corpo(carga: dict[str, object]) -> float | None:
    """Lê `parameters.retry_after` de uma carga já decodificada, se houver."""
    parametros = carga.get("parameters")
    retry_after = parametros.get("retry_after") if isinstance(parametros, dict) else None
    return retry_after if isinstance(retry_after, int | float) else None


def _retry_after_do_corpo_do_erro(erro: urllib.error.HTTPError) -> float | None:
    """Lê `parameters.retry_after` do corpo de um erro 429, se houver.

    É só um extra de conveniência: o corpo pode vir ausente ou ilegível (o teste
    o constrói com `fp=None`), e isso nunca deve impedir a classificação do erro
    pelo código HTTP.
    """
    try:
        carga = json.loads(erro.read())
    except (ValueError, AttributeError, OSError):
        return None
    return _retry_after_do_corpo(carga)
