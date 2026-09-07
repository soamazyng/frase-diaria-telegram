"""Onde as peças concretas se encontram.

Este é o único módulo que conhece ao mesmo tempo a AWS, o Telegram e os casos de
uso. Tudo que ele monta é injetável, para que os testes nunca precisem dele.
"""

import os
from functools import lru_cache

import boto3

from frase_diaria.aplicacao.receber_comando import ReceberComando
from frase_diaria.dominio.autorizacao import PoliticaDeAcesso
from frase_diaria.infraestrutura.relogio import RelogioDoSistema
from frase_diaria.persistencia.comandos import RepositorioDeComandosDynamo
from frase_diaria.telegram.canal import TelegramHttp

PREFIXO_DOS_PARAMETROS = "/frase-diaria/"


@lru_cache(maxsize=1)
def segredos() -> dict[str, str]:
    """Lê os segredos do Parameter Store uma vez por container.

    Cachear no processo evita uma chamada ao SSM por requisição. O ciclo de vida
    do container é curto o bastante para que uma rotação seja absorvida sem
    intervenção; se isso deixar de valer, invalidar este cache é o ponto único.
    """
    cliente = boto3.client("ssm")
    pagina = cliente.get_parameters_by_path(
        Path=PREFIXO_DOS_PARAMETROS, WithDecryption=True, Recursive=False
    )
    return {p["Name"].rsplit("/", 1)[-1]: p["Value"] for p in pagina["Parameters"]}


def montar_receber_comando() -> ReceberComando:
    guardados = segredos()
    dynamo = boto3.resource("dynamodb")
    return ReceberComando(
        politica=PoliticaDeAcesso(
            segredo_esperado=guardados["webhook-secret"],
            chat_id_autorizado=int(guardados["telegram-chat-id"]),
        ),
        repositorio=RepositorioDeComandosDynamo(tabela=dynamo.Table(os.environ["TABELA_ESTADO"])),
        canal=TelegramHttp(token=guardados["telegram-bot-token"]),
        relogio=RelogioDoSistema(),
    )
