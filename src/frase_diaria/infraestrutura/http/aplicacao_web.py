import json
import logging
from typing import Any, Protocol

from fastapi import FastAPI, Request, Response

from frase_diaria.aplicacao.consultar_saude import ConsultarSaude
from frase_diaria.aplicacao.receber_comando import Desfecho
from frase_diaria.infraestrutura.configuracao import versao_da_aplicacao
from frase_diaria.infraestrutura.relogio import RelogioDoSistema

_log = logging.getLogger(__name__)

CABECALHO_DO_SEGREDO = "X-Telegram-Bot-Api-Secret-Token"


class CasoDeReceberComando(Protocol):
    def executar(self, segredo: str | None, corpo: dict[str, Any]) -> Desfecho: ...


def criar_aplicacao(
    versao: str | None = None,
    receber_comando: CasoDeReceberComando | None = None,
) -> FastAPI:
    """Monta a aplicação web e injeta os adaptadores concretos.

    A documentação interativa fica desabilitada: o bot é de usuária única e não
    precisa expor o próprio contrato publicamente.
    """
    consultar_saude = ConsultarSaude(
        relogio=RelogioDoSistema(),
        versao=versao if versao is not None else versao_da_aplicacao(),
    )
    aplicacao = FastAPI(
        title="frase-diaria-telegram",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @aplicacao.get("/health")
    def health() -> dict[str, Any]:
        saude = consultar_saude.executar()
        return {
            "situacao": "ok",
            "versao": saude.versao,
            "instante": saude.instante.isoformat(),
        }

    if receber_comando is not None:

        @aplicacao.post("/telegram/webhook")
        async def webhook(request: Request) -> Response:
            """Recebe um Update do Telegram.

            O código de status governa a reentrega: sucesso encerra, erro faz o
            Telegram tentar de novo. Recusa de acesso e update irrelevante
            respondem 200 porque reentregar não mudaria o resultado; só a falha
            de persistência pede nova entrega.

            A resposta nunca diz por que uma entrada foi recusada.
            """
            bruto = await request.body()
            try:
                corpo = json.loads(bruto)
            except ValueError:
                # Corpo inválido não vira válido numa reentrega.
                _log.warning("corpo do webhook não é JSON; reconhecendo e ignorando")
                return Response(status_code=200)
            if not isinstance(corpo, dict):
                return Response(status_code=200)

            desfecho = receber_comando.executar(
                segredo=request.headers.get(CABECALHO_DO_SEGREDO),
                corpo=corpo,
            )
            if desfecho is Desfecho.NAO_PERSISTIDO:
                return Response(status_code=500)
            return Response(status_code=200)

    return aplicacao
