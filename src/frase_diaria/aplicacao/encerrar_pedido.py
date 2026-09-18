"""Persiste o desfecho de uma entrega e mantém o ciclo coerente."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, assert_never

from frase_diaria.aplicacao.diagnostico import erro_sanitizado
from frase_diaria.aplicacao.entregar_pedido import DesfechoDaEntrega, ResultadoDaEntrega
from frase_diaria.aplicacao.portas import ConflitoDeConcorrencia
from frase_diaria.dominio.ciclo import Ciclo
from frase_diaria.dominio.pedido import MOTIVO_JANELA_ENCERRADA, Pedido

_log = logging.getLogger(__name__)


class RepositorioDePedidosParaEncerramento(Protocol):
    def salvar(self, pedido: Pedido, sequencial: int | None = None) -> None: ...
    def indices_confirmados(self, pedido: str, destinatario: int) -> set[int]: ...
    def indices_incertos(self, pedido: str, destinatario: int) -> set[int]: ...


class RepositorioDeCiclos(Protocol):
    def carregar(self) -> tuple[Ciclo, int]: ...
    def salvar(self, ciclo: Ciclo, versao_anterior: int) -> None:
        """Grava se `versao_anterior` ainda for a versão vigente do ciclo."""
        ...


@dataclass(frozen=True)
class ContextoDoEncerramento:
    ciclo: Ciclo
    versao_do_ciclo: int
    sequencial: int


@dataclass(frozen=True)
class PoliticaDeContencaoDoCiclo:
    esperar: Callable[[float], None]
    dispersao: Callable[[float, float], float]
    max_tentativas: int = 20
    espera_maxima_s: float = 0.02

    def aguardar_nova_tentativa(self) -> None:
        self.esperar(self.dispersao(0, self.espera_maxima_s))


@dataclass(frozen=True)
class EncerrarPedido:
    """Converte desfechos em estados duráveis sem repetir a entrega externa."""

    repositorio: RepositorioDePedidosParaEncerramento
    ciclos: RepositorioDeCiclos
    contencao: PoliticaDeContencaoDoCiclo

    def apos_entrega(self, contexto: ContextoDoEncerramento, entrega: ResultadoDaEntrega) -> Pedido:
        pedido = entrega.pedido
        match entrega.desfecho:
            case DesfechoDaEntrega.JANELA_ESGOTADA:
                return self.expirar(contexto, pedido, MOTIVO_JANELA_ENCERRADA)
            case DesfechoDaEntrega.AGUARDANDO:
                assert entrega.proxima_tentativa is not None
                reagendado = pedido.aguardar_tentativa(
                    erro_sanitizado(entrega.motivo), entrega.proxima_tentativa
                )
                self.repositorio.salvar(reagendado, contexto.sequencial)
                return reagendado
            case DesfechoDaEntrega.INCERTO:
                return self.marcar_incerto(contexto, pedido, entrega.motivo)
            case DesfechoDaEntrega.FALHOU:
                return self._falhar(contexto, entrega)
            case DesfechoDaEntrega.CONCLUIDO:
                concluido = pedido.concluir()
                self.repositorio.salvar(concluido, contexto.sequencial)
                self._consumir(contexto, self._frase_reservada(pedido))
                return concluido
            case _ as desfecho_desconhecido:
                assert_never(desfecho_desconhecido)

    def marcar_incerto(
        self, contexto: ContextoDoEncerramento, pedido: Pedido, motivo: str
    ) -> Pedido:
        incerto = pedido.marcar_incerto(motivo)
        self.repositorio.salvar(incerto, contexto.sequencial)
        if pedido.frase_reservada is not None:
            self._consumir_com_ressalva(contexto, pedido.frase_reservada)
        return incerto

    def sem_conteudo(self, contexto: ContextoDoEncerramento, pedido: Pedido) -> Pedido:
        """Encerra coleção vazia ou uma reserva removida da coleção."""
        houve_confirmacao = self._houve_confirmacao(pedido)
        motivo = (
            "frase reservada não está mais na coleção"
            if pedido.frase_reservada is not None
            else "coleção sem frases elegíveis"
        )
        encerrado = pedido.falhar(alguma_parte_enviada=houve_confirmacao, motivo=motivo)
        # O pedido vem primeiro: uma interrupção deixa o ciclo reconciliável.
        # A ordem inversa poderia soltar uma reserva ainda reivindicada pelo pedido.
        self.repositorio.salvar(encerrado, contexto.sequencial)
        if pedido.frase_reservada is not None:
            if houve_confirmacao:
                self._consumir_com_ressalva(contexto, pedido.frase_reservada)
            else:
                self._liberar(contexto, pedido.frase_reservada)
        return encerrado

    def expirar(self, contexto: ContextoDoEncerramento, pedido: Pedido, motivo: str) -> Pedido:
        """Abandona um pedido que não tem mais chance de nova tentativa.

        Público porque também é chamado fora de `apos_entrega`, por quem
        decide isso antes da entrega — ver `ProcessarPedido._motivo_se_esgotado`.
        """
        if self._tem_incerteza(pedido):
            return self.marcar_incerto(contexto, pedido, motivo)
        houve_confirmacao = self._houve_confirmacao(pedido)
        encerrado = (
            pedido.falhar(alguma_parte_enviada=True, motivo=motivo)
            if houve_confirmacao
            else pedido.expirar(motivo)
        )
        self.repositorio.salvar(encerrado, contexto.sequencial)
        if pedido.frase_reservada is not None:
            if houve_confirmacao:
                self._consumir_com_ressalva(contexto, pedido.frase_reservada)
            else:
                self._liberar(contexto, pedido.frase_reservada)
        return encerrado

    def _falhar(self, contexto: ContextoDoEncerramento, entrega: ResultadoDaEntrega) -> Pedido:
        motivo = erro_sanitizado(entrega.motivo)
        pedido = entrega.pedido
        if self._tem_incerteza(pedido):
            return self.marcar_incerto(contexto, pedido, motivo)
        encerrado = pedido.falhar(
            alguma_parte_enviada=entrega.confirmou_algo,
            motivo=motivo,
        )
        self.repositorio.salvar(encerrado, contexto.sequencial)
        if pedido.frase_reservada is not None:
            if entrega.confirmou_algo:
                self._consumir_com_ressalva(contexto, pedido.frase_reservada)
            else:
                self._liberar(contexto, pedido.frase_reservada)
        return encerrado

    def _consumir(self, contexto: ContextoDoEncerramento, frase: str) -> None:
        self._retentar_no_ciclo(
            contexto,
            continuar=lambda ciclo: not ciclo.foi_consumida(frase),
            transformar=lambda ciclo: self._reservar_se_necessario(ciclo, frase).consumir(
                frase, com_ressalva=False
            ),
        )

    def _consumir_com_ressalva(self, contexto: ContextoDoEncerramento, frase: str) -> None:
        self._retentar_no_ciclo(
            contexto,
            continuar=lambda ciclo: not ciclo.foi_consumida(frase),
            transformar=lambda ciclo: self._reservar_se_necessario(ciclo, frase).consumir(
                frase, com_ressalva=True
            ),
        )

    def _liberar(self, contexto: ContextoDoEncerramento, frase: str) -> None:
        self._retentar_no_ciclo(
            contexto,
            continuar=lambda ciclo: frase in ciclo.reservadas,
            transformar=lambda ciclo: ciclo.liberar(frase),
        )

    @staticmethod
    def _reservar_se_necessario(ciclo: Ciclo, frase: str) -> Ciclo:
        if frase not in ciclo.reservadas:
            _log.warning("ciclo perdeu reserva; consumindo assim mesmo")
            return ciclo.reservar(frase)
        return ciclo

    def _retentar_no_ciclo(
        self,
        contexto: ContextoDoEncerramento,
        continuar: Callable[[Ciclo], bool],
        transformar: Callable[[Ciclo], Ciclo],
    ) -> None:
        ciclo = contexto.ciclo
        versao = contexto.versao_do_ciclo
        for _ in range(self.contencao.max_tentativas):
            if not continuar(ciclo):
                return
            try:
                self.ciclos.salvar(transformar(ciclo), versao)
                return
            except ConflitoDeConcorrencia:
                _log.warning("conflito de concorrência no ciclo; relendo para tentar de novo")
                self.contencao.aguardar_nova_tentativa()
                ciclo, versao = self.ciclos.carregar()
        _log.error("ciclo não avançou após conflitos repetidos; próximo pedido reconcilia")

    def _houve_confirmacao(self, pedido: Pedido) -> bool:
        return any(
            self.repositorio.indices_confirmados(pedido.identidade, destinatario)
            for destinatario in pedido.destinatarios
        )

    def _tem_incerteza(self, pedido: Pedido) -> bool:
        return any(
            self.repositorio.indices_incertos(pedido.identidade, destinatario)
            for destinatario in pedido.destinatarios
        )

    @staticmethod
    def _frase_reservada(pedido: Pedido) -> str:
        if pedido.frase_reservada is None:
            raise ValueError("entrega concluída sem frase reservada")
        return pedido.frase_reservada
