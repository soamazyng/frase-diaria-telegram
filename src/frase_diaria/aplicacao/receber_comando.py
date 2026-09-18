import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from frase_diaria.aplicacao.portas import CriadorDePedidos, ErroDeEnvio, Relogio
from frase_diaria.dominio.atualizacao import Atualizacao
from frase_diaria.dominio.autorizacao import PoliticaDeAcesso, Recusa
from frase_diaria.dominio.comando import Comando
from frase_diaria.dominio.pedido import Origem, Pedido
from frase_diaria.dominio.tempo import politica_do_extra

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

    def reivindicar_acao(self, update_id: int) -> bool: ...
    def liberar_acao(self, update_id: int) -> None: ...
    def marcar_acao_concluida(self, update_id: int) -> None: ...


class CanalDeTelegram(Protocol):
    def enviar_texto(self, chat_id: int, texto: str) -> int: ...


class Despachante(Protocol):
    def acordar(self, identidade: str) -> None:
        """Tenta pôr o worker para trabalhar um pedido agora."""
        ...

    def pedir_status(self, chat_id: int) -> None:
        """Tenta pôr o worker para montar e enviar o relatório de `/status`."""
        ...


class InterpretadorDeAtualizacao(Protocol):
    def __call__(self, corpo: dict[str, Any]) -> Atualizacao | None: ...


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
    interpretar: InterpretadorDeAtualizacao
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

        atualizacao = self.interpretar(corpo)
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
            _log.error("falha ao registrar comando; pedindo reentrega")
            return Desfecho.NAO_PERSISTIDO

        if atualizacao.comando is Comando.FRASE:
            # Antes de decidir sobre a repetição: se a primeira entrega registrou
            # o comando e morreu antes de criar o pedido, é a reentrega que
            # conserta. A criação é idempotente, então repetir é barato.
            try:
                self._pedir_frase(atualizacao.update_id, atualizacao.conversa.chat_id)
            except Exception:
                _log.error("falha ao criar pedido; pedindo reentrega")
                return Desfecho.NAO_PERSISTIDO
            return Desfecho.ACEITO if novo else Desfecho.JA_CONHECIDO

        if atualizacao.comando is Comando.STATUS:
            return self._executar_acao(
                atualizacao.update_id,
                novo,
                lambda: self.despachante.pedir_status(atualizacao.conversa.chat_id),
            )

        return self._executar_acao(
            atualizacao.update_id,
            novo,
            lambda: self.canal.enviar_texto(atualizacao.conversa.chat_id, AJUDA),
        )

    def _executar_acao(self, update_id: int, novo: bool, acao: Callable[[], object]) -> Desfecho:
        """Reivindica uma ação antes do efeito externo e nunca repete ambiguidade."""
        try:
            reivindicada = self.repositorio.reivindicar_acao(update_id)
        except Exception:
            _log.error("falha ao reivindicar ação do comando; pedindo reentrega")
            return Desfecho.NAO_PERSISTIDO
        if not reivindicada:
            return Desfecho.JA_CONHECIDO

        try:
            acao()
        except ErroDeEnvio as erro:
            if erro.resultado_ambiguo:
                _log.error("resultado externo ambíguo; ação não será repetida automaticamente")
                return Desfecho.ACEITO if novo else Desfecho.JA_CONHECIDO
            try:
                self.repositorio.liberar_acao(update_id)
            except Exception:
                _log.error("falha ao liberar ação recusada; ação permanece suspensa")
                return Desfecho.ACEITO if novo else Desfecho.JA_CONHECIDO
            return Desfecho.NAO_PERSISTIDO
        except Exception:
            # Uma conexão pode cair depois que Telegram ou Lambda aceitou a
            # chamada. A reivindicação persistida suspende o reenvio cego.
            _log.error("resultado externo desconhecido; ação não será repetida automaticamente")
            return Desfecho.ACEITO if novo else Desfecho.JA_CONHECIDO

        try:
            self.repositorio.marcar_acao_concluida(update_id)
        except Exception:
            # O efeito externo já ocorreu e a reivindicação continua gravada.
            # Uma reentrega encontra o claim e não duplica a ação.
            _log.error("falha ao confirmar ação; reivindicação impede duplicidade")
        return Desfecho.ACEITO if novo else Desfecho.JA_CONHECIDO

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
            destinatarios=(chat_id,),
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
            _log.error("falha ao acordar o worker; pedido permanece persistido")
