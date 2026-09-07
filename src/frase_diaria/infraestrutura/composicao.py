"""Onde as peças concretas se encontram.

Este é o único módulo que conhece ao mesmo tempo a AWS, o Telegram e os casos de
uso. Tudo que ele monta é injetável, para que os testes nunca precisem dele.
"""

import os
from functools import lru_cache
from typing import Any

import boto3

from frase_diaria.aplicacao.processar_pedido import ProcessarPedido
from frase_diaria.aplicacao.receber_comando import ReceberComando
from frase_diaria.dominio.autorizacao import PoliticaDeAcesso
from frase_diaria.infraestrutura.colecao_fixture import ColecaoFixture
from frase_diaria.infraestrutura.despachante import DespachanteLambda
from frase_diaria.infraestrutura.relogio import RelogioDoSistema
from frase_diaria.infraestrutura.sorteio import SorteioAleatorio
from frase_diaria.persistencia.comandos import RepositorioDeComandosDynamo
from frase_diaria.persistencia.pedidos import RepositorioDePedidosDynamo
from frase_diaria.telegram.canal import TelegramHttp

PREFIXO_DOS_PARAMETROS = "/frase-diaria/"


@lru_cache(maxsize=1)
def segredos() -> dict[str, str]:
    """Lê os segredos do Parameter Store uma vez por container.

    Cachear no processo evita uma chamada ao SSM por requisição. Em contrapartida,
    trocar um parâmetro só vale de imediato depois de republicar — containers
    quentes seguem com o valor antigo.
    """
    cliente = boto3.client("ssm")
    pagina = cliente.get_parameters_by_path(
        Path=PREFIXO_DOS_PARAMETROS, WithDecryption=True, Recursive=False
    )
    return {p["Name"].rsplit("/", 1)[-1]: p["Value"] for p in pagina["Parameters"]}


def _tabela() -> Any:
    return boto3.resource("dynamodb").Table(os.environ["TABELA_ESTADO"])


def montar_receber_comando() -> ReceberComando:
    """A fronteira HTTP: valida, registra e despacha — nunca entrega a frase."""
    guardados = segredos()
    return ReceberComando(
        politica=PoliticaDeAcesso(
            segredo_esperado=guardados["webhook-secret"],
            chat_id_autorizado=int(guardados["telegram-chat-id"]),
        ),
        repositorio=RepositorioDeComandosDynamo(tabela=_tabela()),
        canal=TelegramHttp(token=guardados["telegram-bot-token"]),
        relogio=RelogioDoSistema(),
        pedidos=RepositorioDePedidosDynamo(tabela=_tabela()),
        despachante=DespachanteLambda(
            nome_da_funcao=os.environ["FUNCAO_WORKER"],
            cliente=boto3.client("lambda"),
        ),
    )


def montar_processar_pedido() -> ProcessarPedido:
    """O worker.

    A fonte de frases é a coleção embutida; o ticket 10 troca `ColecaoFixture`
    pelo Notion sem que os casos de uso mudem.
    """
    guardados = segredos()
    return ProcessarPedido(
        repositorio=RepositorioDePedidosDynamo(tabela=_tabela()),
        fonte=ColecaoFixture(),
        canal=TelegramHttp(token=guardados["telegram-bot-token"]),
        sorteio=SorteioAleatorio(),
        relogio=RelogioDoSistema(),
    )
