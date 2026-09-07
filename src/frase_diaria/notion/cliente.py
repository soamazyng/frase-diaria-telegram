import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

BASE = "https://api.notion.com"
VERSAO_DA_API = "2025-09-03"
TAMANHO_DA_PAGINA = 100


class ErroDoNotion(RuntimeError):
    """Falha ao falar com a API do Notion, já sanitizada.

    Nunca carrega o cabeçalho de autorização nem o corpo bruto da resposta.
    """


class AcessoNegado(ErroDoNotion):
    """A API respondeu 403: o token não tem permissão para o recurso pedido."""


@dataclass(frozen=True)
class ClienteNotionHttp:
    """Cliente mínimo da API do Notion sobre a biblioteca padrão.

    Usa `urllib` de propósito, como `telegram/canal.py`: evita uma dependência
    a mais no artefato da Lambda. A paginação de cada endpoint é resolvida
    aqui dentro — quem chama recebe a coleção inteira, ou uma exceção; nunca
    uma lista truncada em silêncio (AC08).
    """

    token: str = field(repr=False)
    timeout_s: float = 10.0
    max_tentativas: int = 3

    def buscar_filhos(self, bloco_id: str) -> tuple[dict[str, Any], ...]:
        """Todos os blocos filhos diretos de `bloco_id`, na ordem da API."""
        return tuple(self._paginar(f"/v1/blocks/{bloco_id}/children"))

    def buscar_comentarios(self, bloco_id: str) -> tuple[dict[str, Any], ...] | None:
        """Discussões nativas associadas ao bloco, ou `None` se o acesso for negado.

        Perder acesso a comentários não invalida a coleção inteira: quem chama
        transforma o `None` em diagnóstico, não em falha de sincronização.
        """
        try:
            return tuple(self._paginar("/v1/comments", {"block_id": bloco_id}))
        except AcessoNegado:
            return None

    def _paginar(
        self, caminho: str, query: dict[str, str] | None = None
    ) -> Iterator[dict[str, Any]]:
        cursor: str | None = None
        while True:
            parametros = dict(query or {})
            parametros["page_size"] = str(TAMANHO_DA_PAGINA)
            if cursor:
                parametros["start_cursor"] = cursor
            carga = self._chamar(caminho, parametros)
            yield from carga.get("results", [])
            if not carga.get("has_more"):
                return
            cursor = carga.get("next_cursor")
            if not cursor:
                # has_more=True sem next_cursor é resposta malformada: sem
                # isto, a próxima volta repetiria a mesma página para sempre.
                raise ErroDoNotion("Notion indicou has_more sem next_cursor")

    def _chamar(self, caminho: str, parametros: dict[str, str]) -> dict[str, Any]:
        url = f"{BASE}{caminho}?{urllib.parse.urlencode(parametros)}"
        requisicao = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": VERSAO_DA_API,
            },
        )
        tentativas_restantes = self.max_tentativas
        while True:
            try:
                with urllib.request.urlopen(requisicao, timeout=self.timeout_s) as resposta:
                    bruto = resposta.read()
                break
            except urllib.error.HTTPError as erro:
                if erro.code == 429 and tentativas_restantes > 1:
                    tentativas_restantes -= 1
                    time.sleep(_espera_de(erro))
                    continue
                if erro.code == 403:
                    raise AcessoNegado("Notion respondeu HTTP 403") from None
                # A URL da chamada não carrega segredo, mas a resposta pode; só
                # o código importa aqui, como no cliente do Telegram.
                raise ErroDoNotion(f"Notion respondeu HTTP {erro.code}") from None
            except urllib.error.URLError:
                raise ErroDoNotion("falha de rede ao chamar o Notion") from None

        try:
            return dict(json.loads(bruto))
        except ValueError:
            raise ErroDoNotion("Notion devolveu resposta ilegível") from None


def _espera_de(erro: urllib.error.HTTPError) -> float:
    """Segundos a esperar antes de tentar de novo um 429, honrando `Retry-After`."""
    valor = erro.headers.get("Retry-After") if erro.headers else None
    try:
        return max(float(valor), 0.0) if valor is not None else 1.0
    except ValueError:
        return 1.0
