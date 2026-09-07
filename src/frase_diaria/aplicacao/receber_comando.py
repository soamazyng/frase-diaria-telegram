import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from frase_diaria.aplicacao.portas import Relogio
from frase_diaria.dominio.autorizacao import PoliticaDeAcesso
from frase_diaria.dominio.comando import Comando
from frase_diaria.dominio.pedido import Origem, Pedido
from frase_diaria.telegram.atualizacao import Atualizacao, interpretar

_log = logging.getLogger(__name__)

AJUDA = (
    "Eu envio uma frase por dia às 08:00.\n\n"
    "/frase — uma frase extra agora\n"
    "/status — como está a operação"
)


class Desfecho(Enum):
    """O que a fronteira HTTP deve responder ao Telegram."""

    ACEITO = "aceito"
    JA_CONHECIDO = "ja_conhecido"
    IGNORADO = "ignorado"
    NAO_PERSISTIDO = "nao_persistido"


class RepositorioDeComandos(Protocol):
    def registrar(self, atualizacao: Atualizacao, instante: datetime) -> bool:
        """Registra o comando. Devolve False se este update já era conhecido."""
        ...


class CanalDeTelegram(Protocol):
    def enviar_texto(self, chat_id: int, texto: str) -> int: ...


class RepositorioDePedidos(Protocol):
    def criar_se_ausente(self, pedido: Pedido, instante: datetime) -> bool: ...


class Despachante(Protocol):
    def acordar(self, identidade: str) -> None:
        """Tenta pôr o worker para trabalhar agora."""
        ...


@dataclass(frozen=True)
class ReceberComando:
    """Recebe um update do webhook e decide o que fazer com ele.

    Duas regras estruturam o método: o comando é persistido **antes** de a
    resposta HTTP confirmar recebimento, e uma conversa não autorizada não
    recebe resposta nem gera pedido.
    """

    politica: PoliticaDeAcesso
    repositorio: RepositorioDeComandos
    canal: CanalDeTelegram
    relogio: Relogio
    pedidos: RepositorioDePedidos
    despachante: Despachante

    def executar(self, segredo: str | None, corpo: dict[str, Any]) -> Desfecho:
        atualizacao = interpretar(corpo)
        if atualizacao is None:
            # Não é mensagem de conversa. Reconhecer e ignorar: devolver erro
            # faria o Telegram reentregar para sempre algo que nunca interessa.
            return Desfecho.IGNORADO

        recusa = self.politica.avaliar(segredo=segredo, conversa=atualizacao.conversa)
        if recusa is not None:
            # Sem resposta e sem pedido. O motivo fica no log, nunca na resposta.
            _log.warning("entrada recusada: %s", recusa.value)
            return Desfecho.IGNORADO

        try:
            novo = self.repositorio.registrar(atualizacao, self.relogio.agora())
        except Exception:
            # Devolver erro faz o Telegram reentregar. Responder à usuária agora
            # deixaria um comando respondido porém não registrado, que voltaria.
            _log.exception("falha ao registrar comando; pedindo reentrega")
            return Desfecho.NAO_PERSISTIDO

        if atualizacao.comando is Comando.FRASE:
            # Antes de decidir sobre a repetição: se a primeira entrega registrou
            # o comando e morreu antes de criar o pedido, é a reentrega que
            # conserta. A criação é idempotente, então repetir é barato.
            try:
                self._pedir_frase(atualizacao.update_id, atualizacao.conversa.chat_id)
            except Exception:
                _log.exception("falha ao criar pedido; pedindo reentrega")
                return Desfecho.NAO_PERSISTIDO
            return Desfecho.ACEITO if novo else Desfecho.JA_CONHECIDO

        if not novo:
            return Desfecho.JA_CONHECIDO

        if atualizacao.comando in (Comando.START, Comando.DESCONHECIDO):
            self.canal.enviar_texto(atualizacao.conversa.chat_id, AJUDA)

        return Desfecho.ACEITO

    def _pedir_frase(self, update_id: int, chat_id: int) -> None:
        """Cria o pedido extra e tenta acordar o worker.

        A frase não é enviada aqui: quem entrega é o worker, lendo o pedido da
        persistência. Responder no webhook exigiria trabalho em segundo plano
        depois da resposta HTTP, que a spec descarta.
        """
        pedido = Pedido(
            identidade=Pedido.identidade_de_extra(update_id),
            origem=Origem.EXTRA,
            chat_id=chat_id,
        )
        if not self.pedidos.criar_se_ausente(pedido, self.relogio.agora()):
            return
        try:
            self.despachante.acordar(pedido.identidade)
        except Exception:
            # O pedido está persistido; o reconciliador o alcançará. Falhar aqui
            # faria o Telegram reentregar um comando já registrado.
            _log.exception("falha ao acordar o worker para %s", pedido.identidade)
