import os

VARIAVEL_DE_VERSAO = "VERSAO_DA_APLICACAO"
VERSAO_EM_DESENVOLVIMENTO = "desenvolvimento"


def versao_da_aplicacao() -> str:
    """Identificador da versão publicada.

    O pipeline injeta o SHA do commit avaliado; fora dele, a execução é local.
    """
    return os.environ.get(VARIAVEL_DE_VERSAO) or VERSAO_EM_DESENVOLVIMENTO
