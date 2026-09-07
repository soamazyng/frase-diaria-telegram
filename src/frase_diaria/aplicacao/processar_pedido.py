import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ClassVar, Protocol

from frase_diaria.aplicacao.diagnostico import erro_sanitizado
from frase_diaria.aplicacao.portas import ConflitoDeConcorrencia, Relogio, Sorteio
from frase_diaria.dominio.ciclo import Ciclo
from frase_diaria.dominio.frase import Frase
from frase_diaria.dominio.pedido import EstadoDoPedido, Pedido
from frase_diaria.dominio.selecao import SemFrase, selecionar
from frase_diaria.telegram.canal import MESSAGE_ID_DESCONHECIDO, ErroDoTelegram

_log = logging.getLogger(__name__)


class RepositorioDePedidos(Protocol):
    def obter(self, identidade: str) -> Pedido | None: ...
    def assumir_lease(
        self, pedido: str, sequencial: int, agora: datetime, duracao: timedelta
    ) -> None: ...
    def salvar(self, pedido: Pedido, sequencial: int | None = None) -> None: ...
    def registrar_intencao_parte(
        self, pedido: str, indice: int, texto: str, instante: datetime
    ) -> None: ...
    def confirmar_parte(
        self,
        pedido: str,
        indice: int,
        texto: str,
        message_id: int,
        instante: datetime,
        sequencial: int | None = None,
    ) -> None: ...
    def marcar_parte_incerta(
        self, pedido: str, indice: int, motivo: str, instante: datetime
    ) -> None: ...
    def indices_confirmados(self, pedido: str) -> set[int]: ...
    def indices_incertos(self, pedido: str) -> set[int]: ...
    def indices_intencoes(self, pedido: str) -> set[int]: ...
    def registrar_tentativa(
        self, pedido: str, resultado: str, erro: str | None, instante: datetime
    ) -> int: ...
    def finalizar_tentativa(
        self, pedido: str, sequencial: int, resultado: str, erro: str | None, instante: datetime
    ) -> None: ...


class FonteDeFrases(Protocol):
    def listar(self) -> tuple[Frase, ...]: ...


class RepositorioDeCiclos(Protocol):
    def carregar(self) -> tuple[Ciclo, int]: ...
    def salvar(self, ciclo: Ciclo, versao_anterior: int) -> None:
        """Grava se `versao_anterior` ainda for a versão vigente do ciclo."""
        ...


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

    O sequencial de tentativa (de `registrar_tentativa`, atômico e monotônico)
    dobra como token do lease: é o que impede um executor superado — porque
    outra execução do mesmo evento já avançou o pedido — de confirmar entrega ou
    avançar o ciclo depois de perder a corrida (spec, 4.9; AC03).
    """

    repositorio: RepositorioDePedidos
    fonte: FonteDeFrases
    canal: CanalDeEnvio
    sorteio: Sorteio
    relogio: Relogio
    ciclos: RepositorioDeCiclos
    reserva: Reserva

    DURACAO_DO_LEASE: ClassVar[timedelta] = timedelta(minutes=5)
    # Regravar o ciclo depois de um conflito não chama o Telegram nem repete
    # nada visível à usuária — só relê e tenta de novo um item pequeno do
    # DynamoDB. O teto existe para não travar a Lambda para sempre se a
    # condição nunca puder ser satisfeita; não para poupar chamadas caras.
    MAX_TENTATIVAS_DE_CICLO: ClassVar[int] = 20
    # Sob contenção real, vários pedidos colidem na mesma gravação ao mesmo
    # tempo; sem dispersão, todos relêem e tentam de novo juntos, colidindo de
    # novo. Um jitter pequeno já quebra essa sincronia (achado do code-review).
    ESPERA_MAXIMA_ENTRE_TENTATIVAS_S: ClassVar[float] = 0.02

    def executar(self, identidade: str) -> Pedido | None:
        pedido = self.repositorio.obter(identidade)
        if pedido is None:
            _log.warning("pedido não encontrado")
            return None
        if pedido.estado.terminal:
            # Estado terminal não reabre: um disparo duplicado não reenvia.
            return pedido
        if pedido.proxima_tentativa is not None and pedido.proxima_tentativa > self.relogio.agora():
            return pedido

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
        escolha = self._escolher(pedido, ciclo)

        if escolha is SemFrase.AGUARDANDO_RESERVA:
            # Transitório: outro pedido segura a última frase livre. Encerrar
            # aqui levaria o pedido a estado terminal, de onde nem a retomada nem
            # a janela de recuperação o tirariam.
            motivo = "todas as frases reservadas"
            self.repositorio.salvar(pedido.aguardar_tentativa(motivo), sequencial)
            raise ReservaPendente(motivo)
        if escolha is SemFrase.COLECAO_VAZIA:
            return self._encerrar_sem_conteudo(pedido, ciclo, versao_ciclo, sequencial)

        frase, ciclo = escolha
        if pedido.frase_reservada is None:
            # Ciclo e pedido em uma transação: gravar um sem o outro deixaria uma
            # reserva órfã que nada libera, travando o ciclo para sempre.
            candidato = pedido.reservar(frase.identidade)
            try:
                self.reserva.efetivar(candidato, ciclo, versao_ciclo, sequencial)
            except ConflitoDeConcorrencia as conflito:
                # Outro executor já avançou o ciclo a partir da mesma versão que
                # lemos: a transação inteira foi recusada, então `pedido` — não
                # `candidato` — segue refletindo o que está de fato persistido.
                # Uma nova tentativa relê tudo do zero (ticket 09).
                _log.warning("conflito de concorrência ao reservar; nova tentativa retomará")
                motivo = "conflito de concorrência ao reservar frase"
                self.repositorio.salvar(pedido.aguardar_tentativa(motivo), sequencial)
                raise ReservaPendente(motivo) from conflito
            pedido = candidato
            # `reserva.efetivar` acabou de persistir a versão seguinte: sem isto,
            # o consumo logo abaixo tentaria gravar com a versão já superada e
            # cairia na retentativa por engano, mesmo sem nenhuma concorrência.
            versao_ciclo += 1

        if pedido.estado is not EstadoDoPedido.ENVIANDO:
            pedido = pedido.iniciar_envio()
            self.repositorio.salvar(pedido, sequencial)
        return self._entregar(pedido, frase, ciclo, versao_ciclo, sequencial)

    def _escolher(self, pedido: Pedido, ciclo: Ciclo) -> tuple[Frase, Ciclo] | SemFrase:
        """Decide qual frase entregar, respeitando o ciclo.

        A reserva existente vence o sorteio: uma nova tentativa reutiliza a frase
        já reservada, porque sortear outra deixaria a primeira consumida sem ter
        sido entregue (spec, 4.4).
        """
        disponiveis = self.fonte.listar()
        por_identidade = {f.identidade: f for f in disponiveis}

        if pedido.frase_reservada is not None:
            frase = por_identidade.get(pedido.frase_reservada)
            return SemFrase.COLECAO_VAZIA if frase is None else (frase, ciclo)

        escolha = selecionar(ciclo, tuple(por_identidade), self.sorteio)
        if isinstance(escolha, SemFrase):
            return escolha
        identidade, ciclo = escolha
        return por_identidade[identidade], ciclo

    def _encerrar_sem_conteudo(
        self, pedido: Pedido, ciclo: Ciclo, versao_ciclo: int, sequencial: int
    ) -> Pedido:
        """Não há frase para entregar: ou a coleção está vazia, ou a reservada sumiu.

        Consultar as partes já confirmadas antes de decidir é o que preserva a
        invariante: quem já entregou alguma parte mantém a frase consumida, ainda
        que ela tenha desaparecido da fonte.
        """
        ja_entregou = bool(self.repositorio.indices_confirmados(pedido.identidade))
        motivo = (
            "frase reservada não está mais na coleção"
            if pedido.frase_reservada is not None
            else "coleção sem frases elegíveis"
        )
        encerrado = pedido.falhar(alguma_parte_enviada=ja_entregou, motivo=motivo)
        # Pedido primeiro: um crash depois disto deixa o ciclo desatualizado, que
        # é recuperável; a ordem inversa deixaria o pedido reivindicando uma
        # reserva que o ciclo já soltou, e a retomada reentregaria a frase.
        self.repositorio.salvar(encerrado, sequencial)
        if pedido.frase_reservada is not None:
            self._encerrar_no_ciclo(ciclo, versao_ciclo, pedido.frase_reservada, ja_entregou)
        return encerrado

    def _encerrar_no_ciclo(
        self, ciclo: Ciclo, versao_ciclo: int, frase: str, alguma_enviada: bool
    ) -> None:
        """Consumo só depois de entrega confirmada.

        Nada entregue devolve a frase às elegíveis. Entrega parcial marca consumo
        **com ressalva**: a frase conta como gasta, para não reenviar
        automaticamente algo que já pode ter chegado, e a dúvida fica registrada.
        """
        if alguma_enviada:
            self._consumir_no_ciclo(ciclo, versao_ciclo, frase, com_ressalva=True)
            return
        self._retentar_no_ciclo(
            ciclo,
            versao_ciclo,
            continuar=lambda c: frase in c.reservadas,
            transformar=lambda c: c.liberar(frase),
        )

    def _consumir_no_ciclo(
        self, ciclo: Ciclo, versao_ciclo: int, frase: str, com_ressalva: bool
    ) -> None:
        """Marca a frase como gasta, mesmo que o ciclo tenha perdido a reserva.

        Perder a reserva é sinal de divergência — uma gravação concorrente
        sobrescreveu o ciclo, por exemplo. Pular o consumo em silêncio deixaria
        uma frase já entregue elegível de novo no mesmo ciclo, quebrando o
        sorteio sem repetição. Registrar e consumir mesmo assim é o desfecho
        correto: a mensagem foi para a usuária.
        """

        def transformar(c: Ciclo) -> Ciclo:
            if frase not in c.reservadas:
                _log.warning("ciclo perdeu reserva; consumindo assim mesmo")
                c = c.reservar(frase)
            return c.consumir(frase, com_ressalva=com_ressalva)

        self._retentar_no_ciclo(
            ciclo,
            versao_ciclo,
            continuar=lambda c: not c.foi_consumida(frase),
            transformar=transformar,
        )

    def _retentar_no_ciclo(
        self,
        ciclo: Ciclo,
        versao_ciclo: int,
        *,
        continuar: Callable[[Ciclo], bool],
        transformar: Callable[[Ciclo], Ciclo],
    ) -> None:
        """Regrava o ciclo, relendo e reaplicando a mudança se perder a corrida.

        Diárias e extras compartilham o mesmo item de ciclo: dois pedidos
        distintos podem terminar ao mesmo tempo e disputar a mesma gravação. Um
        conflito de versão aqui não é motivo para abortar o pedido — que já está
        em estado terminal a esta altura —, só para reler o ciclo e tentar de
        novo (ticket 09). Esgotadas as tentativas, desiste e registra: o próximo
        pedido que tocar a mesma frase reconcilia a divergência.
        """
        for _ in range(self.MAX_TENTATIVAS_DE_CICLO):
            if not continuar(ciclo):
                return
            try:
                self.ciclos.salvar(transformar(ciclo), versao_ciclo)
                return
            except ConflitoDeConcorrencia:
                _log.warning("conflito de concorrência no ciclo; relendo para tentar de novo")
                time.sleep(random.uniform(0, self.ESPERA_MAXIMA_ENTRE_TENTATIVAS_S))
                ciclo, versao_ciclo = self.ciclos.carregar()
        _log.error("ciclo não avançou após conflitos repetidos; próximo pedido reconcilia")

    def _entregar(
        self, pedido: Pedido, frase: Frase, ciclo: Ciclo, versao_ciclo: int, sequencial: int
    ) -> Pedido:
        ja_confirmadas = self.repositorio.indices_confirmados(pedido.identidade)
        ja_incertas: set[int] = getattr(self.repositorio, "indices_incertos", lambda *_: set())(
            pedido.identidade
        )
        alguma_enviada = bool(ja_confirmadas)

        for indice, texto in enumerate(frase.partes):
            if indice in ja_confirmadas or indice in ja_incertas:
                continue
            indices_intencoes: set[int] = getattr(
                self.repositorio, "indices_intencoes", lambda *_: set()
            )(pedido.identidade)
            if indice in indices_intencoes:
                motivo = "intenção registrada sem confirmação; reenvio automático suspenso"
                return self._marcar_incerto(
                    pedido, motivo, alguma_enviada, ciclo, versao_ciclo, sequencial
                )
            registrar_intencao = getattr(self.repositorio, "registrar_intencao_parte", None)
            if registrar_intencao is not None:
                registrar_intencao(pedido.identidade, indice, texto, self.relogio.agora())
            try:
                message_id = self.canal.enviar_texto(pedido.chat_id, texto)
            except ErroDoTelegram as erro:
                # A mensagem já vem sanitizada do canal: sem token, sem URL.
                return self._encerrar_com_falha(
                    pedido, str(erro), alguma_enviada, ciclo, versao_ciclo, sequencial
                )
            if message_id == MESSAGE_ID_DESCONHECIDO:
                motivo = "Telegram pode ter aceitado a parte, mas não houve confirmação durável"
                marcar_incerta = getattr(self.repositorio, "marcar_parte_incerta", None)
                if marcar_incerta is not None:
                    marcar_incerta(pedido.identidade, indice, motivo, self.relogio.agora())
                return self._marcar_incerto(
                    pedido, motivo, alguma_enviada, ciclo, versao_ciclo, sequencial
                )
            # Confirmação persistida com o texto efetivamente enviado: o histórico
            # preserva o que chegou, mesmo que a origem mude depois. A condição do
            # lease garante que um executor superado não confirma nada (AC03) —
            # `ConflitoDeConcorrencia` propaga até `executar`, que trata o caso.
            self.repositorio.confirmar_parte(
                pedido.identidade, indice, texto, message_id, self.relogio.agora(), sequencial
            )
            alguma_enviada = True

        concluido = pedido.concluir()
        self.repositorio.salvar(concluido, sequencial)
        # Consumo definitivo: todas as partes confirmadas.
        self._consumir_no_ciclo(ciclo, versao_ciclo, frase.identidade, com_ressalva=False)
        return concluido

    def _marcar_incerto(
        self,
        pedido: Pedido,
        motivo: str,
        alguma_enviada: bool,
        ciclo: Ciclo,
        versao_ciclo: int,
        sequencial: int,
    ) -> Pedido:
        incerto = pedido.marcar_incerto(motivo)
        self.repositorio.salvar(incerto, sequencial)
        if pedido.frase_reservada is not None:
            self._encerrar_no_ciclo(ciclo, versao_ciclo, pedido.frase_reservada, alguma_enviada)
        return incerto

    def _encerrar_com_falha(
        self,
        pedido: Pedido,
        erro: str,
        alguma_enviada: bool,
        ciclo: Ciclo,
        versao_ciclo: int,
        sequencial: int,
    ) -> Pedido:
        erro = erro_sanitizado(erro)
        encerrado = pedido.falhar(alguma_parte_enviada=alguma_enviada, motivo=erro)
        self.repositorio.salvar(encerrado, sequencial)
        if pedido.frase_reservada is not None:
            self._encerrar_no_ciclo(ciclo, versao_ciclo, pedido.frase_reservada, alguma_enviada)
        return encerrado
