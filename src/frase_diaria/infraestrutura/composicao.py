"""Onde as peças concretas se encontram.

Este é o único módulo que conhece ao mesmo tempo a AWS, o Telegram e os casos de
uso. Tudo que ele monta é injetável, para que os testes nunca precisem dele.
"""

import os
from functools import lru_cache
from typing import Any

import boto3

from frase_diaria.aplicacao.processar_pedido import ProcessarPedido
from frase_diaria.aplicacao.receber_comando import Desfecho, ReceberComando
from frase_diaria.aplicacao.sincronizar_colecao import SincronizarColecao
from frase_diaria.dominio.autorizacao import PoliticaDeAcesso
from frase_diaria.infraestrutura.despachante import DespachanteLambda
from frase_diaria.infraestrutura.fonte_notion import FonteDeFrasesNotion
from frase_diaria.infraestrutura.relogio import RelogioDoSistema
from frase_diaria.infraestrutura.sorteio import SorteioAleatorio
from frase_diaria.notion.cliente import ClienteNotionHttp
from frase_diaria.notion.leitura import LeitorDeColecao
from frase_diaria.persistencia.ciclos import RepositorioDeCiclosDynamo
from frase_diaria.persistencia.colecao import RepositorioDeColecaoDynamo
from frase_diaria.persistencia.comandos import RepositorioDeComandosDynamo
from frase_diaria.persistencia.pedidos import RepositorioDePedidosDynamo
from frase_diaria.persistencia.reserva import ReservaTransacional
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
    # Paginado: `get_parameters_by_path` devolve no máximo 10 por chamada, e uma
    # leitura de página única passaria a faltar segredos silenciosamente quando o
    # projeto crescer (o token do Notion chega no ticket 10).
    paginas = cliente.get_paginator("get_parameters_by_path").paginate(
        Path=PREFIXO_DOS_PARAMETROS, WithDecryption=True, Recursive=False
    )
    return {
        p["Name"].rsplit("/", 1)[-1]: p["Value"] for pagina in paginas for p in pagina["Parameters"]
    }


@lru_cache(maxsize=1)
def _tabela() -> Any:
    """Um recurso por container: construir um `boto3.resource` custa tempo."""
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
        pedidos=RepositorioDePedidosDynamo(
            tabela=_tabela(), bot_legado=guardados["telegram-bot-legado-id"]
        ),
        bot=guardados["telegram-bot-token"].split(":", 1)[0],
        despachante=DespachanteLambda(
            nome_da_funcao=os.environ["FUNCAO_WORKER"],
            cliente=boto3.client("lambda"),
        ),
    )


def montar_processar_pedido() -> ProcessarPedido:
    """O worker.

    A fonte de frases sincroniza com o Notion a cada chamada (spec, 4.2),
    usando o snapshot persistido como cache quando a sincronização falha
    (AC09). A conversão do conteúdo preservado para texto plano em
    `FonteDeFrasesNotion` é um placeholder até a renderização rica do
    ticket 12.
    """
    guardados = segredos()
    relogio = RelogioDoSistema()
    sincronizar = SincronizarColecao(
        leitor=LeitorDeColecao(ClienteNotionHttp(token=guardados["notion-token"])),
        repositorio=RepositorioDeColecaoDynamo(tabela=_tabela()),
        pagina_id=guardados["notion-pagina-id"],
        relogio=relogio,
    )
    return ProcessarPedido(
        repositorio=RepositorioDePedidosDynamo(
            tabela=_tabela(),
            versao=os.environ["VERSAO_DA_APLICACAO"],
            bot_legado=guardados["telegram-bot-legado-id"],
        ),
        fonte=FonteDeFrasesNotion(sincronizar=sincronizar),
        canal=TelegramHttp(token=guardados["telegram-bot-token"]),
        sorteio=SorteioAleatorio(),
        relogio=relogio,
        ciclos=RepositorioDeCiclosDynamo(tabela=_tabela()),
        reserva=ReservaTransacional(
            tabela=_tabela(), bot_legado=guardados["telegram-bot-legado-id"]
        ),
    )


class ReceberComandoPreguicoso:
    """Adia a montagem do caso de uso até a primeira requisição do webhook.

    Montar no import faria `GET /health` depender do SSM: um parâmetro ausente ou
    o serviço indisponível derrubariam também o diagnóstico, e a verificação
    pós-publicação do pipeline reprovaria por dependência em vez de por saúde —
    justamente o contrário do que ela existe para medir.
    """

    @lru_cache(maxsize=1)  # noqa: B019
    def _caso(self) -> ReceberComando:
        return montar_receber_comando()

    def aceita_segredo(self, segredo: str | None) -> bool:
        return self._caso().aceita_segredo(segredo)

    def executar(self, segredo: str | None, corpo: dict[str, Any]) -> Desfecho:
        return self._caso().executar(segredo, corpo)
