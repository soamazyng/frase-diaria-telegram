import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import ClassVar, Protocol

from frase_diaria.aplicacao.diagnostico import erro_sanitizado
from frase_diaria.aplicacao.encerrar_pedido import (
    ContextoDoEncerramento,
    EncerrarPedido,
    RepositorioDeCiclos,
)
from frase_diaria.aplicacao.entregar_pedido import EntregadorDePedido
from frase_diaria.aplicacao.portas import (
    ConflitoDeConcorrencia,
    Relogio,
)
from frase_diaria.dominio.ciclo import Ciclo
from frase_diaria.dominio.frase import Frase
from frase_diaria.dominio.pedido import (
    MOTIVO_JANELA_ENCERRADA,
    MOTIVO_TENTATIVA_UNICA_ESGOTADA,
    EstadoDoPedido,
    Pedido,
)
from frase_diaria.dominio.selecao import SemFrase, Sorteio, selecionar

_log = logging.getLogger(__name__)


class RepositorioDePedidos(Protocol):
    def obter(self, identidade: str) -> Pedido | None: ...
    def assumir_lease(
        self, pedido: str, sequencial: int, agora: datetime, duracao: timedelta
    ) -> None: ...
    def salvar(self, pedido: Pedido, sequencial: int | None = None) -> None: ...
    def indices_confirmados(self, pedido: str, destinatario: int) -> set[int]: ...
    def indices_incertos(self, pedido: str, destinatario: int) -> set[int]: ...
    def indices_intencoes(self, pedido: str, destinatario: int) -> set[int]: ...
    def registrar_tentativa(
        self, pedido: str, resultado: str, erro: str | None, instante: datetime
    ) -> int: ...
    def finalizar_tentativa(
        self, pedido: str, sequencial: int, resultado: str, erro: str | None, instante: datetime
    ) -> None: ...


class FonteDeFrases(Protocol):
    def listar(self) -> tuple[Frase, ...]: ...


class Reserva(Protocol):
    def efetivar(
        self, pedido: Pedido, ciclo: Ciclo, versao_anterior_do_ciclo: int, sequencial: int
    ) -> None:
        """Grava a reserva no ciclo e no pedido atomicamente."""
        ...


class ReservaPendente(RuntimeError):
    """Não há frase livre agora, mas haverá quando a reserva em curso terminar.

    Condição transitória: propagar em vez de encerrar o pedido é o que permite
    uma nova tentativa alcançá-lo.
    """


@dataclass(frozen=True)
class ProcessarPedido:
    """Transforma um pedido persistido em mensagens entregues.

    O worker lê o pedido da persistência — nunca do corpo de uma requisição — de
    modo que uma execução interrompida possa ser retomada por qualquer disparo
    posterior, incluindo o reconciliador.

    O sequencial de tentativa (de `registrar_tentativa`, atômico e monotônico)
    dobra como token do lease: é o que impede um executor superado — porque
    outra execução do mesmo evento já avançou o pedido — de confirmar entrega ou
    avançar o ciclo depois de perder a corrida (spec, 4.9; AC03).
    """

    repositorio: RepositorioDePedidos
    fonte: FonteDeFrases
    entregador: EntregadorDePedido
    encerrador: EncerrarPedido
    sorteio: Sorteio
    relogio: Relogio
    ciclos: RepositorioDeCiclos
    reserva: Reserva

    DURACAO_DO_LEASE: ClassVar[timedelta] = timedelta(minutes=5)
    # Observabilidade (spec, 4.8): quando uma tentativa roda bem depois do
    # instante em que estava agendada, vale registrar — sinal de fila
    # acumulando ou disparo atrasado, não de um comportamento errado.
    LIMITE_DE_ATRASO: ClassVar[timedelta] = timedelta(minutes=15)

    def executar(self, identidade: str) -> Pedido | None:
        pedido = self.repositorio.obter(identidade)
        if pedido is None:
            _log.warning("pedido não encontrado")
            return None
        if pedido.estado.terminal:
            # Estado terminal não reabre: um disparo duplicado não reenvia.
            return pedido
        agora = self.relogio.agora()
        if pedido.proxima_tentativa is not None and pedido.proxima_tentativa > agora:
            return pedido
        if pedido.proxima_tentativa is not None and agora - pedido.proxima_tentativa > (
            self.LIMITE_DE_ATRASO
        ):
            _log.warning(
                "tentativa atrasada em mais de %d minutos além do agendado",
                self.LIMITE_DE_ATRASO.total_seconds() // 60,
            )

        sequencial = self.repositorio.registrar_tentativa(
            pedido.identidade, "iniciada", None, self.relogio.agora()
        )
        try:
            self.repositorio.assumir_lease(
                pedido.identidade, sequencial, self.relogio.agora(), self.DURACAO_DO_LEASE
            )
        except ConflitoDeConcorrencia as conflito:
            # Outra execução do mesmo evento já assumiu o lease: esta encerra
            # sem tocar o pedido, para não disputar um estado que já não é seu.
            _log.warning("lease do pedido pertence a outro executor; tentativa abortada")
            self.repositorio.finalizar_tentativa(
                pedido.identidade,
                sequencial,
                "aguardando",
                erro_sanitizado(str(conflito)),
                self.relogio.agora(),
            )
            return pedido
        try:
            resultado = self._processar(pedido, sequencial)
        except ReservaPendente as pendente:
            self.repositorio.finalizar_tentativa(
                pedido.identidade,
                sequencial,
                "aguardando",
                erro_sanitizado(str(pendente)),
                self.relogio.agora(),
            )
            raise
        except ConflitoDeConcorrencia as conflito:
            # Um sequencial mais novo assumiu o lease no meio do processamento:
            # esta execução foi superada, não falhou. Devolve o pedido como lido
            # no início — não um estado parcial desta tentativa abandonada.
            _log.warning("lease perdido durante o processamento; execução superada abandona")
            self.repositorio.finalizar_tentativa(
                pedido.identidade,
                sequencial,
                "superado",
                erro_sanitizado(str(conflito)),
                self.relogio.agora(),
            )
            return pedido
        except Exception:
            self.repositorio.finalizar_tentativa(
                pedido.identidade, sequencial, "erro", "erro de integração", self.relogio.agora()
            )
            raise RuntimeError("processamento interrompido; consultar tentativa") from None
        self.repositorio.finalizar_tentativa(
            pedido.identidade,
            sequencial,
            resultado.estado.value,
            None if resultado.estado is EstadoDoPedido.ENVIADO else resultado.motivo_do_estado,
            self.relogio.agora(),
        )
        return resultado

    def _processar(self, pedido: Pedido, sequencial: int) -> Pedido:
        ciclo, versao_ciclo = self.ciclos.carregar()
        contexto = ContextoDoEncerramento(ciclo, versao_ciclo, sequencial)
        retomada_suspensa = self.entregador.suspender_retomada_sem_snapshot(pedido, sequencial)
        if retomada_suspensa is not None:
            return self.encerrador.marcar_incerto(contexto, pedido, retomada_suspensa.motivo)
        motivo_do_esgotamento = self._motivo_se_esgotado(pedido, sequencial)
        if motivo_do_esgotamento is not None:
            return self.encerrador.expirar(contexto, pedido, motivo_do_esgotamento)
        escolha = self._escolher(pedido, ciclo)

        if escolha is SemFrase.AGUARDANDO_RESERVA:
            # Transitório: outro pedido segura a última frase livre. Encerrar
            # aqui levaria o pedido a estado terminal, de onde nem a retomada nem
            # a janela de recuperação o tirariam.
            motivo = "todas as frases reservadas"
            self.repositorio.salvar(pedido.aguardar_tentativa(motivo), sequencial)
            raise ReservaPendente(motivo)
        if escolha is SemFrase.COLECAO_VAZIA:
            return self.encerrador.sem_conteudo(contexto, pedido)

        frase, ciclo = escolha
        pedido_para_reservar = pedido
        if pedido.frase_reservada is not None and pedido.frase_reservada != frase.identidade:
            # `_escolher` já liberou a reserva antiga no ciclo devolvido; falta
            # só sair do estado atual antes de reservar a nova frase abaixo.
            # `pedido` (a variável externa) continua intocado até a transação
            # confirmar: se ela falhar, ele ainda é a única referência à
            # reserva antiga, que segue persistida no ciclo (ver except abaixo).
            pedido_para_reservar = pedido.liberar_frase_excluida(
                "frase reservada não está mais na coleção; selecionando outra"
            )

        if pedido_para_reservar.frase_reservada is None:
            # Ciclo e pedido em uma transação: gravar um sem o outro deixaria uma
            # reserva órfã que nada libera, travando o ciclo para sempre.
            candidato = replace(
                pedido_para_reservar.reservar(frase.identidade),
                partes_reservadas=frase.partes,
            )
            try:
                self.reserva.efetivar(candidato, ciclo, versao_ciclo, sequencial)
            except ConflitoDeConcorrencia as conflito:
                # A transação inteira foi recusada — nem a reserva antiga foi
                # liberada, nem a nova foi efetivada. Gravar `pedido_para_reservar`
                # (frase_reservada=None) aqui órfãos a reserva antiga no ciclo:
                # nenhum pedido mais a referenciaria para liberá-la depois. `pedido`
                # segue refletindo o que está de fato persistido; uma nova
                # tentativa relê tudo do zero e retoma a troca (ticket 09).
                _log.warning("conflito de concorrência ao reservar; nova tentativa retomará")
                motivo = "conflito de concorrência ao reservar frase"
                self.repositorio.salvar(pedido.aguardar_tentativa(motivo), sequencial)
                raise ReservaPendente(motivo) from conflito
            pedido = candidato
            # `reserva.efetivar` acabou de persistir a versão seguinte: sem isto,
            # o consumo logo abaixo tentaria gravar com a versão já superada e
            # cairia na retentativa por engano, mesmo sem nenhuma concorrência.
            versao_ciclo += 1
        else:
            pedido = pedido_para_reservar

        if (
            pedido.estado is not EstadoDoPedido.ENVIANDO
            or pedido.total_de_partes != len(frase.partes)
            or pedido.partes_reservadas != frase.partes
        ):
            if pedido.estado is not EstadoDoPedido.ENVIANDO:
                pedido = pedido.iniciar_envio()
            pedido = replace(
                pedido,
                total_de_partes=len(frase.partes),
                partes_reservadas=frase.partes,
            )
            self.repositorio.salvar(pedido, sequencial)
        entrega = self.entregador.entregar(pedido, frase, sequencial)
        return self.encerrador.apos_entrega(
            ContextoDoEncerramento(ciclo, versao_ciclo, sequencial),
            entrega,
        )

    def _motivo_se_esgotado(self, pedido: Pedido, sequencial: int) -> str | None:
        """Motivo de encerramento se não há mais chance de nova tentativa, senão `None`.

        `EntregadorDePedido` já respeita prazo e tentativa única, mas só
        dentro do envio de cada parte. Uma falha ANTES da entrega — na
        sincronização com o Notion, por exemplo — nunca alcança essa checagem,
        então sem esta aqui um pedido assim retenta para sempre: achado real
        de produção, um `/frase` com 836 tentativas ao longo de mais de um dia,
        muito além do prazo. `sequencial == 1` é sempre a primeira tentativa
        (spec, 4.5: a tentativa única precisa rodar, cedo ou tarde).
        """
        if pedido.prazo_vencido(self.relogio.agora()):
            return MOTIVO_JANELA_ENCERRADA
        if pedido.tentativa_unica and sequencial > 1:
            return MOTIVO_TENTATIVA_UNICA_ESGOTADA
        return None

    def _escolher(self, pedido: Pedido, ciclo: Ciclo) -> tuple[Frase, Ciclo] | SemFrase:
        """Decide qual frase entregar, respeitando o ciclo.

        A reserva existente vence o sorteio: uma nova tentativa reutiliza a frase
        já reservada, porque sortear outra deixaria a primeira consumida sem ter
        sido entregue (spec, 4.4). Se a frase reservada sumiu da fonte (edição
        que a excluiu) e nada foi entregue ainda, a reserva é liberada e a
        seleção roda de novo como se o pedido nunca tivesse reservado nada —
        trocar no meio de uma entrega parcial quebraria a invariante de que uma
        frase é uma entrega lógica única, por isso só acontece sem nada
        confirmado (spec, 4.2).
        """
        disponiveis = self.fonte.listar()
        por_identidade = {f.identidade: f for f in disponiveis}

        if pedido.frase_reservada is not None:
            if pedido.partes_reservadas is not None and self._algum_destinatario_iniciou(pedido):
                return Frase(pedido.frase_reservada, pedido.partes_reservadas), ciclo
            frase = por_identidade.get(pedido.frase_reservada)
            if frase is not None:
                return frase, ciclo
            if self._algum_destinatario_confirmou(pedido):
                return SemFrase.COLECAO_VAZIA
            if pedido.frase_reservada in ciclo.reservadas:
                ciclo = ciclo.liberar(pedido.frase_reservada)

        escolha = selecionar(ciclo, tuple(por_identidade), self.sorteio)
        if isinstance(escolha, SemFrase):
            return escolha
        identidade, ciclo = escolha
        return por_identidade[identidade], ciclo

    def _algum_destinatario_iniciou(self, pedido: Pedido) -> bool:
        return any(
            self.repositorio.indices_confirmados(pedido.identidade, destinatario)
            or self.repositorio.indices_incertos(pedido.identidade, destinatario)
            or self.repositorio.indices_intencoes(pedido.identidade, destinatario)
            for destinatario in pedido.destinatarios
        )

    def _algum_destinatario_confirmou(self, pedido: Pedido) -> bool:
        """Se a frase já chegou, confirmada, a pelo menos um destinatário.

        É o que decide se a frase fica consumida-com-ressalva (nunca mais
        reoferecida, para não duplicar a quem já recebeu) ou é liberada de
        volta ao ciclo (nada confirmado a ninguém ainda). Generaliza o que
        antes da v2 era "esta única conversa recebeu alguma parte" — agora é
        "algum destinatário deste pedido recebeu alguma parte" (spec v2).
        """
        return any(
            self.repositorio.indices_confirmados(pedido.identidade, destinatario)
            for destinatario in pedido.destinatarios
        )
