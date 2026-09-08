import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from frase_diaria.aplicacao.portas import CriadorDePedidos, Relogio
from frase_diaria.dominio.autorizacao import PoliticaDeAcesso, Recusa
from frase_diaria.dominio.comando import Comando
from frase_diaria.dominio.pedido import Origem, Pedido
from frase_diaria.dominio.tempo import politica_do_extra
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


class Despachante(Protocol):
    def acordar(self, identidade: str) -> None:
        """Tenta pôr o worker para trabalhar um pedido agora."""
        ...

    def pedir_status(self, chat_id: int) -> None:
        """Tenta pôr o worker para montar e enviar o relatório de `/status`."""
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
    pedidos: CriadorDePedidos
    despachante: Despachante
    bot: str = "principal"

    def aceita_segredo(self, segredo: str | None) -> bool:
        """Permite à fronteira HTTP recusar antes mesmo de ler o corpo."""
        return self.politica.conferir_segredo(segredo) is None

    def executar(self, segredo: str | None, corpo: dict[str, Any]) -> Desfecho:
        # O segredo primeiro, antes de qualquer leitura do corpo: decidir que um
        # update é irrelevante antes disso daria a qualquer origem uma resposta
        # 200 e uma linha de log.
        if self.politica.conferir_segredo(segredo) is not None:
            _log.warning("entrada recusada: %s", Recusa.SEGREDO_INVALIDO.value)
            return Desfecho.IGNORADO

        atualizacao = interpretar(corpo)
        if atualizacao is None:
            # Não é mensagem de conversa. Reconhecer e ignorar: devolver erro
            # faria o Telegram reentregar para sempre algo que nunca interessa.
            return Desfecho.IGNORADO

        recusa = self.politica.conferir_conversa(atualizacao.conversa)
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

        if atualizacao.comando is Comando.STATUS:
            self._pedir_status(atualizacao.conversa.chat_id)
            return Desfecho.ACEITO

        self._responder_ajuda(atualizacao.conversa.chat_id)
        return Desfecho.ACEITO

    def _responder_ajuda(self, chat_id: int) -> None:
        """Envia a ajuda em melhor esforço.

        Falhar aqui não vira 5xx: a reentrega encontraria o comando já
        registrado, devolveria sucesso sem responder, e a usuária nunca receberia
        nada. Como repetir `/start` é trivial e não consome frase, registrar a
        falha e devolver 200 é melhor que uma reentrega que não pode dar certo.
        """
        try:
            self.canal.enviar_texto(chat_id, AJUDA)
        except Exception:
            _log.exception("falha ao enviar a ajuda; a usuária pode repetir o comando")

    def _pedir_status(self, chat_id: int) -> None:
        """Pede ao worker que monte e envie o relatório de `/status`.

        Igual à ajuda: melhor esforço. O comando já está registrado, então
        devolver erro aqui só faria o Telegram reentregar algo já reconhecido
        — e a reentrega cairia direto em `JA_CONHECIDO`, sem despachar de novo.
        """
        try:
            self.despachante.pedir_status(chat_id)
        except Exception:
            _log.exception("falha ao pedir o status ao worker; sem reconciliador para isto")

    def _pedir_frase(self, update_id: int, chat_id: int) -> None:
        """Cria o pedido extra e tenta acordar o worker.

        A frase não é enviada aqui: quem entrega é o worker, lendo o pedido da
        persistência. Responder no webhook exigiria trabalho em segundo plano
        depois da resposta HTTP, que a spec descarta.
        """
        agora = self.relogio.agora()
        politica = politica_do_extra(agora)
        pedido = Pedido(
            identidade=Pedido.identidade_de_extra(self.bot, update_id),
            origem=Origem.EXTRA,
            chat_id=chat_id,
            prazo=politica.prazo,
            tentativa_unica=politica.tentativa_unica,
        )
        self.pedidos.criar_se_ausente(pedido, agora)
        # Acordar mesmo quando o pedido já existia: a execução anterior pode ter
        # criado o pedido e morrido antes do despacho, e o worker é idempotente.
        try:
            self.despachante.acordar(pedido.identidade)
        except Exception:
            # O pedido está persistido; o reconciliador o alcançará. Falhar aqui
            # faria o Telegram reentregar um comando já registrado.
            _log.exception("falha ao acordar o worker; pedido permanece persistido")
