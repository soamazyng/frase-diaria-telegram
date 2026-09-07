from typing import Any

from fastapi import FastAPI

from frase_diaria.aplicacao.consultar_saude import ConsultarSaude
from frase_diaria.infraestrutura.configuracao import versao_da_aplicacao
from frase_diaria.infraestrutura.relogio import RelogioDoSistema


def criar_aplicacao(versao: str | None = None) -> FastAPI:
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

    return aplicacao
