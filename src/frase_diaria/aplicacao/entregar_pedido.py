"""Entrega as partes de uma frase e relata o desfecho agregado."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import ClassVar, Protocol

from frase_diaria.aplicacao.portas import (
    ID_DE_MENSAGEM_DESCONHECIDO,
    ChaveDeParte,
    ConfirmacaoDeParte,
    ConteudoConfirmado,
    ErroDeEnvio,
    IncertezaDeParte,
    IntencaoDeParte,
    Relogio,
    TentativaDeParte,
)
from frase_diaria.dominio.frase import Frase
from frase_diaria.dominio.pedido import Pedido


class RepositorioDeEntrega(Protocol):
    def salvar(self, pedido: Pedido, sequencial: int | None = None) -> None: ...
    def registrar_intencao_parte(self, intencao: IntencaoDeParte) -> None: ...
    def descartar_intencao_parte(self, chave: ChaveDeParte, sequencial: int) -> None: ...
    def confirmar_parte(self, confirmacao: ConfirmacaoDeParte) -> None: ...
    def marcar_parte_incerta(self, incerteza: IncertezaDeParte) -> None: ...
    def indices_confirmados(self, pedido: str, destinatario: int) -> set[int]: ...
    def indices_incertos(self, pedido: str, destinatario: int) -> set[int]: ...
    def indices_intencoes(self, pedido: str, destinatario: int) -> set[int]: ...


class CanalDeEnvio(Protocol):
    def enviar_texto(self, chat_id: int, texto: str) -> int:
        """Envia e devolve o identificador atribuído pelo canal externo."""
        ...


class DesfechoDaEntrega(Enum):
    CONCLUIDO = "concluido"
    INCERTO = "incerto"
    FALHOU = "falhou"
    AGUARDANDO = "aguardando"
    JANELA_ESGOTADA = "janela_esgotada"


@dataclass(frozen=True)
class ResultadoDaEntrega:
    pedido: Pedido
    desfecho: DesfechoDaEntrega
    motivo: str = ""
    proxima_tentativa: datetime | None = None
    confirmou_algo: bool = False

    def __post_init__(self) -> None:
        aguardando = self.desfecho is DesfechoDaEntrega.AGUARDANDO
        if aguardando != (self.proxima_tentativa is not None):
            raise ValueError("entrega aguardando exige próxima tentativa exclusiva")


@dataclass(frozen=True)
class _ResultadoDoDestinatario:
    desfecho: DesfechoDaEntrega
    motivo: str
    proxima_tentativa: datetime | None = None
    confirmou_algo: bool = False


@dataclass(frozen=True)
class _TentativaDeEntrega:
    pedido: Pedido
    destinatario: int
    sequencial: int


@dataclass(frozen=True)
class EntregadorDePedido:
    """Entrega uma frase sem decidir o estado terminal nem alterar o ciclo."""

    repositorio: RepositorioDeEntrega
    canal: CanalDeEnvio
    relogio: Relogio
    dispersao: Callable[[float, float], float]

    BASE_DO_BACKOFF_S: ClassVar[float] = 30.0
    TETO_DO_BACKOFF_S: ClassVar[float] = 900.0
    PROPORCAO_DE_DISPERSAO: ClassVar[float] = 0.1

    def suspender_retomada_sem_snapshot(
        self, pedido: Pedido, sequencial: int
    ) -> ResultadoDaEntrega | None:
        """Converte rastros legados sem conteúdo congelado em incerteza durável."""
        if pedido.frase_reservada is None or pedido.partes_reservadas is not None:
            return None
        intencoes = [
            (destinatario, indice)
            for destinatario in pedido.destinatarios
            for indice in sorted(
                self.repositorio.indices_intencoes(pedido.identidade, destinatario)
            )
        ]
        tem_incerteza = any(
            self.repositorio.indices_incertos(pedido.identidade, destinatario)
            for destinatario in pedido.destinatarios
        )
        if not intencoes and not tem_incerteza:
            return None

        motivo = "intenção legada sem snapshot; reenvio automático suspenso"
        for destinatario, indice in intencoes:
            self._registrar_incerteza_da_parte(
                _TentativaDeEntrega(pedido, destinatario, sequencial), indice, motivo
            )
        return ResultadoDaEntrega(pedido, DesfechoDaEntrega.INCERTO, motivo)

    def entregar(self, pedido: Pedido, frase: Frase, sequencial: int) -> ResultadoDaEntrega:
        """Tenta todos os destinatários e devolve o pior desfecho observado."""
        resultados: list[_ResultadoDoDestinatario] = []
        for destinatario in pedido.destinatarios:
            tentativa = _TentativaDeEntrega(pedido, destinatario, sequencial)
            resultado = self._entregar_a_destinatario(tentativa, frase)
            resultados.append(resultado)
            if (
                resultado.desfecho is DesfechoDaEntrega.FALHOU
                and destinatario not in pedido.destinatarios_com_falha
            ):
                pedido = replace(
                    pedido,
                    destinatarios_com_falha=(*pedido.destinatarios_com_falha, destinatario),
                )
                self.repositorio.salvar(pedido, sequencial)
            if resultado.desfecho is DesfechoDaEntrega.JANELA_ESGOTADA:
                break

        motivo = self._motivo_agregado(resultados)
        confirmou_algo = any(resultado.confirmou_algo for resultado in resultados)

        if self._tem_desfecho(resultados, DesfechoDaEntrega.JANELA_ESGOTADA):
            return ResultadoDaEntrega(
                pedido, DesfechoDaEntrega.JANELA_ESGOTADA, motivo, confirmou_algo=confirmou_algo
            )

        aguardando = [
            resultado
            for resultado in resultados
            if resultado.desfecho is DesfechoDaEntrega.AGUARDANDO
        ]
        if aguardando:
            proximas = [
                resultado.proxima_tentativa
                for resultado in aguardando
                if resultado.proxima_tentativa is not None
            ]
            return ResultadoDaEntrega(
                pedido,
                DesfechoDaEntrega.AGUARDANDO,
                motivo,
                proxima_tentativa=max(proximas),
                confirmou_algo=confirmou_algo,
            )

        if self._tem_desfecho(resultados, DesfechoDaEntrega.INCERTO):
            return ResultadoDaEntrega(
                pedido, DesfechoDaEntrega.INCERTO, motivo, confirmou_algo=confirmou_algo
            )
        if self._tem_desfecho(resultados, DesfechoDaEntrega.FALHOU):
            return ResultadoDaEntrega(
                pedido, DesfechoDaEntrega.FALHOU, motivo, confirmou_algo=confirmou_algo
            )
        return ResultadoDaEntrega(
            pedido, DesfechoDaEntrega.CONCLUIDO, confirmou_algo=confirmou_algo
        )

    @staticmethod
    def _tem_desfecho(
        resultados: list[_ResultadoDoDestinatario], desfecho: DesfechoDaEntrega
    ) -> bool:
        return any(resultado.desfecho is desfecho for resultado in resultados)

    @staticmethod
    def _motivo_agregado(resultados: list[_ResultadoDoDestinatario]) -> str:
        motivos = [
            resultado.motivo
            for resultado in resultados
            if resultado.desfecho is not DesfechoDaEntrega.CONCLUIDO
        ]
        return "; ".join(motivos)

    def _entregar_a_destinatario(
        self, tentativa: _TentativaDeEntrega, frase: Frase
    ) -> _ResultadoDoDestinatario:
        """Retoma somente partes pendentes e preserva desfechos definitivos."""
        pedido = tentativa.pedido
        destinatario = tentativa.destinatario
        confirmadas = self.repositorio.indices_confirmados(pedido.identidade, destinatario)
        confirmou_algo = bool(confirmadas)
        if destinatario in pedido.destinatarios_com_falha:
            return _ResultadoDoDestinatario(
                DesfechoDaEntrega.FALHOU,
                "falha definitiva registrada",
                confirmou_algo=confirmou_algo,
            )
        incertas = self.repositorio.indices_incertos(pedido.identidade, destinatario)
        for indice, texto in enumerate(frase.partes):
            if indice in confirmadas or indice in incertas:
                continue
            resultado = self._entregar_parte(tentativa, indice, texto)
            if resultado.desfecho is not DesfechoDaEntrega.CONCLUIDO:
                return replace(resultado, confirmou_algo=confirmou_algo)
            confirmou_algo = True

        if incertas:
            return _ResultadoDoDestinatario(
                DesfechoDaEntrega.INCERTO,
                "há parte sem confirmação durável; reenvio automático suspenso",
                confirmou_algo=confirmou_algo,
            )
        return _ResultadoDoDestinatario(
            DesfechoDaEntrega.CONCLUIDO, "", confirmou_algo=confirmou_algo
        )

    def _entregar_parte(
        self, tentativa: _TentativaDeEntrega, indice: int, texto: str
    ) -> _ResultadoDoDestinatario:
        pedido = tentativa.pedido
        if pedido.prazo is not None and self.relogio.agora() >= pedido.prazo:
            return _ResultadoDoDestinatario(
                DesfechoDaEntrega.JANELA_ESGOTADA, "janela de recuperação encerrada"
            )
        intencoes = self.repositorio.indices_intencoes(pedido.identidade, tentativa.destinatario)
        if indice in intencoes:
            return self._registrar_incerteza_da_parte(
                tentativa,
                indice,
                "intenção registrada sem confirmação; reenvio automático suspenso",
            )

        chave = ChaveDeParte(pedido.identidade, tentativa.destinatario, indice)
        self.repositorio.registrar_intencao_parte(
            IntencaoDeParte(
                chave=chave,
                texto=texto,
                tentativa=TentativaDeParte(self.relogio.agora(), tentativa.sequencial),
            )
        )
        try:
            message_id = self.canal.enviar_texto(tentativa.destinatario, texto)
        except ErroDeEnvio as erro:
            if erro.resultado_ambiguo:
                return self._registrar_incerteza_da_parte(tentativa, indice, str(erro))
            self.repositorio.descartar_intencao_parte(chave, tentativa.sequencial)
            return self._resultado_da_falha(tentativa, erro)
        if message_id == ID_DE_MENSAGEM_DESCONHECIDO:
            return self._registrar_incerteza_da_parte(
                tentativa,
                indice,
                "Telegram pode ter aceitado a parte, mas não houve confirmação durável",
            )
        # Confirmar com o mesmo sequencial garante que o lease ainda pertence
        # a esta execução quando a entrega externa se torna durável.
        self.repositorio.confirmar_parte(
            ConfirmacaoDeParte(
                chave=chave,
                conteudo=ConteudoConfirmado(texto, message_id),
                tentativa=TentativaDeParte(self.relogio.agora(), tentativa.sequencial),
            )
        )
        return _ResultadoDoDestinatario(DesfechoDaEntrega.CONCLUIDO, "")

    def _registrar_incerteza_da_parte(
        self, tentativa: _TentativaDeEntrega, indice: int, motivo: str
    ) -> _ResultadoDoDestinatario:
        self.repositorio.marcar_parte_incerta(
            IncertezaDeParte(
                chave=ChaveDeParte(
                    tentativa.pedido.identidade,
                    tentativa.destinatario,
                    indice,
                ),
                motivo=motivo,
                tentativa=TentativaDeParte(self.relogio.agora(), tentativa.sequencial),
            )
        )
        return _ResultadoDoDestinatario(DesfechoDaEntrega.INCERTO, motivo)

    def _resultado_da_falha(
        self, tentativa: _TentativaDeEntrega, erro: ErroDeEnvio
    ) -> _ResultadoDoDestinatario:
        pedido = tentativa.pedido
        if (
            erro.transitorio
            and not pedido.tentativa_unica
            and (pedido.prazo is None or self.relogio.agora() < pedido.prazo)
        ):
            proximo = self._proximo_instante_de_tentativa(tentativa.sequencial, erro.retry_after_s)
            return _ResultadoDoDestinatario(DesfechoDaEntrega.AGUARDANDO, str(erro), proximo)
        return _ResultadoDoDestinatario(DesfechoDaEntrega.FALHOU, str(erro))

    def _proximo_instante_de_tentativa(
        self, sequencial: int, retry_after_s: float | None
    ) -> datetime:
        """Aplica o limite externo ou um backoff exponencial com dispersão."""
        if retry_after_s is not None:
            atraso = float(retry_after_s)
        else:
            atraso = min(self.BASE_DO_BACKOFF_S * (2 ** (sequencial - 1)), self.TETO_DO_BACKOFF_S)
            atraso += self.dispersao(0, atraso * self.PROPORCAO_DE_DISPERSAO)
        return self.relogio.agora() + timedelta(seconds=atraso)
