import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from frase_diaria.aplicacao.portas import Relogio, Sorteio
from frase_diaria.dominio.frase import Frase
from frase_diaria.dominio.pedido import Pedido
from frase_diaria.telegram.canal import ErroDoTelegram

_log = logging.getLogger(__name__)


class RepositorioDePedidos(Protocol):
    def obter(self, identidade: str) -> Pedido | None: ...
    def salvar(self, pedido: Pedido) -> None: ...
    def confirmar_parte(
        self, pedido: str, indice: int, texto: str, message_id: int, instante: datetime
    ) -> None: ...
    def indices_confirmados(self, pedido: str) -> set[int]: ...
    def registrar_tentativa(
        self, pedido: str, resultado: str, erro: str | None, instante: datetime
    ) -> None: ...


class FonteDeFrases(Protocol):
    def listar(self) -> tuple[Frase, ...]: ...


class CanalDeEnvio(Protocol):
    def enviar_texto(self, chat_id: int, texto: str) -> int:
        """Envia e devolve o message_id atribuído pelo Telegram."""
        ...


@dataclass(frozen=True)
class ProcessarPedido:
    """Transforma um pedido persistido em mensagens entregues.

    O worker lê o pedido da persistência — nunca do corpo de uma requisição — de
    modo que uma execução interrompida possa ser retomada por qualquer disparo
    posterior, incluindo o reconciliador.
    """

    repositorio: RepositorioDePedidos
    fonte: FonteDeFrases
    canal: CanalDeEnvio
    sorteio: Sorteio
    relogio: Relogio

    def executar(self, identidade: str) -> Pedido | None:
        pedido = self.repositorio.obter(identidade)
        if pedido is None:
            _log.warning("pedido %s não encontrado", identidade)
            return None
        if pedido.estado.terminal:
            # Estado terminal não reabre: um disparo duplicado não reenvia.
            return pedido

        frase = self._frase_para(pedido)
        if frase is None:
            return self._encerrar_sem_conteudo(pedido)

        if pedido.frase_reservada is None:
            pedido = pedido.reservar(frase.identidade)
            self.repositorio.salvar(pedido)

        return self._entregar(pedido, frase)

    def _frase_para(self, pedido: Pedido) -> Frase | None:
        """A reserva existente vence o sorteio.

        Uma nova tentativa reutiliza a frase já reservada; sortear outra deixaria
        a primeira consumida sem ter sido entregue (spec, 4.4).
        """
        disponiveis = self.fonte.listar()
        if pedido.frase_reservada is not None:
            return next((f for f in disponiveis if f.identidade == pedido.frase_reservada), None)
        if not disponiveis:
            return None
        return self.sorteio.escolher(disponiveis)

    def _encerrar_sem_conteudo(self, pedido: Pedido) -> Pedido:
        """Não há frase para entregar: ou a coleção está vazia, ou a reservada sumiu.

        Consultar as partes já confirmadas antes de decidir é o que preserva a
        invariante: quem já entregou alguma parte mantém a frase consumida, ainda
        que ela tenha desaparecido da fonte.
        """
        agora = self.relogio.agora()
        ja_entregou = bool(self.repositorio.indices_confirmados(pedido.identidade))
        motivo = (
            "frase reservada não está mais na coleção"
            if pedido.frase_reservada is not None
            else "coleção sem frases elegíveis"
        )
        encerrado = pedido.falhar(alguma_parte_enviada=ja_entregou)
        self.repositorio.salvar(encerrado)
        self.repositorio.registrar_tentativa(pedido.identidade, "falhou", motivo, agora)
        return encerrado

    def _entregar(self, pedido: Pedido, frase: Frase) -> Pedido:
        ja_confirmadas = self.repositorio.indices_confirmados(pedido.identidade)
        alguma_enviada = bool(ja_confirmadas)

        for indice, texto in enumerate(frase.partes):
            if indice in ja_confirmadas:
                continue
            try:
                message_id = self.canal.enviar_texto(pedido.chat_id, texto)
            except ErroDoTelegram as erro:
                # A mensagem já vem sanitizada do canal: sem token, sem URL.
                return self._encerrar_com_falha(pedido, str(erro), alguma_enviada)
            except Exception as erro:
                # Falha que não é do Telegram: registra o que aconteceu e deixa
                # subir. Propagar é o que faz a Lambda retentar; engolir deixaria
                # o pedido preso em ENVIANDO, sem rastro e sem quem o retomasse.
                _log.exception("erro inesperado ao entregar %s", pedido.identidade)
                self.repositorio.registrar_tentativa(
                    pedido.identidade, "erro", repr(erro), self.relogio.agora()
                )
                raise
            # Confirmação persistida com o texto efetivamente enviado: o histórico
            # preserva o que chegou, mesmo que a origem mude depois.
            self.repositorio.confirmar_parte(
                pedido.identidade, indice, texto, message_id, self.relogio.agora()
            )
            alguma_enviada = True

        concluido = pedido.concluir()
        self.repositorio.salvar(concluido)
        self.repositorio.registrar_tentativa(
            pedido.identidade, "enviado", None, self.relogio.agora()
        )
        return concluido

    def _encerrar_com_falha(self, pedido: Pedido, erro: str, alguma_enviada: bool) -> Pedido:
        encerrado = pedido.falhar(alguma_parte_enviada=alguma_enviada)
        self.repositorio.salvar(encerrado)
        self.repositorio.registrar_tentativa(
            pedido.identidade, "falhou", erro, self.relogio.agora()
        )
        return encerrado
