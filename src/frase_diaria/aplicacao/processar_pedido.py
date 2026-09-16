import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
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
        self, pedido: str, destinatario: int, indice: int, texto: str, instante: datetime
    ) -> None: ...
    def confirmar_parte(
        self,
        pedido: str,
        destinatario: int,
        indice: int,
        texto: str,
        message_id: int,
        instante: datetime,
        sequencial: int | None = None,
    ) -> None: ...
    def marcar_parte_incerta(
        self,
        pedido: str,
        destinatario: int,
        indice: int,
        motivo: str,
        instante: datetime,
        sequencial: int,
    ) -> None: ...
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


class _DesfechoDoDestinatario(Enum):
    """O que aconteceu ao tentar entregar a frase a UM destinatário.

    Isolado por construção: o desfecho de um destinatário nunca depende do
    desfecho de outro. `_entregar` (abaixo) decide o estado agregado do
    pedido só depois de tentar todos, exatamente para que uma falha
    permanente num destinatário não impeça a tentativa aos demais (spec v2,
    `.scratch/v2-telegram-bot.md`).
    """

    CONCLUIDO = "concluido"
    INCERTO = "incerto"
    FALHOU = "falhou"
    AGUARDANDO = "aguardando"
    JANELA_ESGOTADA = "janela_esgotada"


@dataclass(frozen=True)
class _ResultadoDoDestinatario:
    desfecho: _DesfechoDoDestinatario
    motivo: str
    proxima_tentativa: datetime | None = None
    # Evita reler as confirmações ao decidir o consumo no ciclo.
    confirmou_algo: bool = False


@dataclass(frozen=True)
class _TentativaDeEntrega:
    pedido: Pedido
    destinatario: int
    sequencial: int


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
    # novo. Um jitter pequeno evita repetir a mesma disputa entre workers.
    ESPERA_MAXIMA_ENTRE_TENTATIVAS_S: ClassVar[float] = 0.02
    # Espera progressiva entre tentativas após um erro transitório do Telegram
    # (AC13): dobra a cada tentativa, com um teto para não deixar um pedido
    # preso a um atraso enorme, e uma dispersão para não sincronizar retentativas
    # de pedidos diferentes que falharam no mesmo instante.
    BASE_DO_BACKOFF_S: ClassVar[float] = 30.0
    TETO_DO_BACKOFF_S: ClassVar[float] = 900.0
    PROPORCAO_DE_DISPERSAO: ClassVar[float] = 0.1
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
            candidato = pedido_para_reservar.reservar(frase.identidade)
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

        if pedido.estado is not EstadoDoPedido.ENVIANDO or pedido.total_de_partes != len(
            frase.partes
        ):
            if pedido.estado is not EstadoDoPedido.ENVIANDO:
                pedido = pedido.iniciar_envio()
            pedido = replace(pedido, total_de_partes=len(frase.partes))
            self.repositorio.salvar(pedido, sequencial)
        return self._entregar(pedido, frase, ciclo, versao_ciclo, sequencial)

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

    def _encerrar_por_janela_esgotada(
        self, pedido: Pedido, ciclo: Ciclo, versao_ciclo: int, sequencial: int
    ) -> Pedido:
        """O prazo do pedido já passou: abandona em vez de tentar entregar.

        Nada enviado ainda vira EXPIRADO — mais preciso que FALHOU para "o tempo
        acabou", sem confundir com uma recusa do Telegram. Alguma parte já
        confirmada precisa continuar PARCIAL, com a mesma ressalva de consumo de
        qualquer outra entrega incompleta (spec, 4.4; AC14).
        """
        motivo = "janela de recuperação encerrada"
        if self._algum_destinatario_tem_incerteza(pedido):
            return self._marcar_incerto(pedido, motivo, ciclo, versao_ciclo, sequencial)
        alguma_enviada = self._algum_destinatario_confirmou(pedido)
        encerrado = (
            pedido.falhar(alguma_parte_enviada=True, motivo=motivo)
            if alguma_enviada
            else pedido.expirar(motivo)
        )
        self.repositorio.salvar(encerrado, sequencial)
        if pedido.frase_reservada is not None:
            self._encerrar_no_ciclo(ciclo, versao_ciclo, pedido.frase_reservada, alguma_enviada)
        return encerrado

    def _encerrar_sem_conteudo(
        self, pedido: Pedido, ciclo: Ciclo, versao_ciclo: int, sequencial: int
    ) -> Pedido:
        """Não há frase para entregar: ou a coleção está vazia, ou a reservada sumiu.

        Consultar as partes já confirmadas antes de decidir é o que preserva a
        invariante: quem já entregou alguma parte mantém a frase consumida, ainda
        que ela tenha desaparecido da fonte.
        """
        ja_entregou = self._algum_destinatario_confirmou(pedido)
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
            continuar=lambda ciclo_atual: frase in ciclo_atual.reservadas,
            transformar=lambda ciclo_atual: ciclo_atual.liberar(frase),
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

        def transformar(ciclo_atual: Ciclo) -> Ciclo:
            if frase not in ciclo_atual.reservadas:
                _log.warning("ciclo perdeu reserva; consumindo assim mesmo")
                ciclo_atual = ciclo_atual.reservar(frase)
            return ciclo_atual.consumir(frase, com_ressalva=com_ressalva)

        self._retentar_no_ciclo(
            ciclo,
            versao_ciclo,
            continuar=lambda ciclo_atual: not ciclo_atual.foi_consumida(frase),
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
        """Entrega a frase a cada destinatário, isoladamente.

        A falha definitiva de um destinatário é preservada sem impedir a
        tentativa dos demais (spec v2). A janela esgotada interrompe a passada:
        um prazo vencido interrompe a passada imediatamente, porque não faz
        sentido tentar mais ninguém depois do prazo. O estado agregado do
        pedido só é decidido depois de ver todos os desfechos, na ordem
        janela > aguardando > incerto > falhou > concluído — a pior notícia
        entre os destinatários é o que controla se o pedido retenta.
        """
        varios_destinatarios = len(pedido.destinatarios) > 1
        resultados: list[tuple[int, _ResultadoDoDestinatario]] = []
        for destinatario in pedido.destinatarios:
            resultado = self._entregar_a_destinatario(pedido, destinatario, frase, sequencial)
            resultados.append((destinatario, resultado))
            if (
                resultado.desfecho is _DesfechoDoDestinatario.FALHOU
                and destinatario not in pedido.destinatarios_com_falha
            ):
                pedido = replace(
                    pedido,
                    destinatarios_com_falha=(*pedido.destinatarios_com_falha, destinatario),
                )
                self.repositorio.salvar(pedido, sequencial)
            if resultado.desfecho is _DesfechoDoDestinatario.JANELA_ESGOTADA:
                break

        def _motivo_agregado() -> str:
            """Preserva todos os desfechos, inclusive os que não decidiram o agregado."""
            problematicos = [
                (destinatario, resultado)
                for destinatario, resultado in resultados
                if resultado.desfecho is not _DesfechoDoDestinatario.CONCLUIDO
            ]
            if not varios_destinatarios:
                return problematicos[0][1].motivo if problematicos else ""
            return "; ".join(
                f"{resultado.motivo} (destinatário {destinatario})"
                for destinatario, resultado in problematicos
            )

        if any(r.desfecho is _DesfechoDoDestinatario.JANELA_ESGOTADA for _, r in resultados):
            return self._encerrar_por_janela_esgotada(pedido, ciclo, versao_ciclo, sequencial)

        aguardando = [r for _, r in resultados if r.desfecho is _DesfechoDoDestinatario.AGUARDANDO]
        if aguardando:
            # O instante mais tardio entre os que aguardam — não o primeiro do
            # tuple: respeita o retry_after de todos os destinatários (AC13).
            proximas = [r.proxima_tentativa for r in aguardando if r.proxima_tentativa is not None]
            return self._reagendar_apos_falha_transitoria(
                pedido, _motivo_agregado(), sequencial, max(proximas)
            )

        alguma_enviada = any(resultado.confirmou_algo for _, resultado in resultados)

        if any(r.desfecho is _DesfechoDoDestinatario.INCERTO for _, r in resultados):
            return self._marcar_incerto(pedido, _motivo_agregado(), ciclo, versao_ciclo, sequencial)

        if any(r.desfecho is _DesfechoDoDestinatario.FALHOU for _, r in resultados):
            return self._encerrar_com_falha(
                pedido, _motivo_agregado(), alguma_enviada, ciclo, versao_ciclo, sequencial
            )

        # Todos os destinatários concluíram: consumo definitivo, uma única vez,
        # independentemente de quantos destinatários o pedido tinha.
        concluido = pedido.concluir()
        self.repositorio.salvar(concluido, sequencial)
        self._consumir_no_ciclo(ciclo, versao_ciclo, frase.identidade, com_ressalva=False)
        return concluido

    def _entregar_a_destinatario(
        self, pedido: Pedido, destinatario: int, frase: Frase, sequencial: int
    ) -> _ResultadoDoDestinatario:
        """Retoma somente partes pendentes e preserva os desfechos definitivos."""
        confirmadas = self.repositorio.indices_confirmados(pedido.identidade, destinatario)
        confirmou_algo = bool(confirmadas)
        if destinatario in pedido.destinatarios_com_falha:
            return _ResultadoDoDestinatario(
                _DesfechoDoDestinatario.FALHOU,
                "falha definitiva registrada",
                confirmou_algo=confirmou_algo,
            )
        incertas = self.repositorio.indices_incertos(pedido.identidade, destinatario)
        tentativa = _TentativaDeEntrega(pedido, destinatario, sequencial)
        for indice, texto in enumerate(frase.partes):
            if indice in confirmadas or indice in incertas:
                continue
            resultado = self._entregar_parte(tentativa, indice, texto)
            if resultado.desfecho is not _DesfechoDoDestinatario.CONCLUIDO:
                return replace(resultado, confirmou_algo=confirmou_algo)
            confirmou_algo = True

        if incertas:
            return _ResultadoDoDestinatario(
                _DesfechoDoDestinatario.INCERTO,
                "há parte sem confirmação durável; reenvio automático suspenso",
                confirmou_algo=confirmou_algo,
            )
        return _ResultadoDoDestinatario(
            _DesfechoDoDestinatario.CONCLUIDO, "", confirmou_algo=confirmou_algo
        )

    def _entregar_parte(
        self, tentativa: _TentativaDeEntrega, indice: int, texto: str
    ) -> _ResultadoDoDestinatario:
        pedido = tentativa.pedido
        # O prazo é conferido por parte; o envio anterior pode ter atravessado a janela.
        if pedido.prazo is not None and self.relogio.agora() >= pedido.prazo:
            return _ResultadoDoDestinatario(
                _DesfechoDoDestinatario.JANELA_ESGOTADA, "janela de recuperação encerrada"
            )
        intencoes = self.repositorio.indices_intencoes(pedido.identidade, tentativa.destinatario)
        if indice in intencoes:
            return self._registrar_incerteza_da_parte(
                tentativa,
                indice,
                "intenção registrada sem confirmação; reenvio automático suspenso",
            )

        self.repositorio.registrar_intencao_parte(
            pedido.identidade, tentativa.destinatario, indice, texto, self.relogio.agora()
        )
        try:
            message_id = self.canal.enviar_texto(tentativa.destinatario, texto)
        except ErroDoTelegram as erro:
            return self._resultado_da_falha(tentativa, erro)
        if message_id == MESSAGE_ID_DESCONHECIDO:
            return self._registrar_incerteza_da_parte(
                tentativa,
                indice,
                "Telegram pode ter aceitado a parte, mas não houve confirmação durável",
            )
        # O lease precisa continuar vigente quando a confirmação for persistida.
        self.repositorio.confirmar_parte(
            pedido.identidade,
            tentativa.destinatario,
            indice,
            texto,
            message_id,
            self.relogio.agora(),
            tentativa.sequencial,
        )
        return _ResultadoDoDestinatario(_DesfechoDoDestinatario.CONCLUIDO, "")

    def _registrar_incerteza_da_parte(
        self, tentativa: _TentativaDeEntrega, indice: int, motivo: str
    ) -> _ResultadoDoDestinatario:
        self.repositorio.marcar_parte_incerta(
            tentativa.pedido.identidade,
            tentativa.destinatario,
            indice,
            motivo,
            self.relogio.agora(),
            tentativa.sequencial,
        )
        return _ResultadoDoDestinatario(_DesfechoDoDestinatario.INCERTO, motivo)

    def _resultado_da_falha(
        self, tentativa: _TentativaDeEntrega, erro: ErroDoTelegram
    ) -> _ResultadoDoDestinatario:
        pedido = tentativa.pedido
        if (
            erro.transitorio
            and not pedido.tentativa_unica
            and (pedido.prazo is None or self.relogio.agora() < pedido.prazo)
        ):
            proximo = self._proximo_instante_de_tentativa(tentativa.sequencial, erro.retry_after_s)
            return _ResultadoDoDestinatario(_DesfechoDoDestinatario.AGUARDANDO, str(erro), proximo)
        return _ResultadoDoDestinatario(_DesfechoDoDestinatario.FALHOU, str(erro))

    def _proximo_instante_de_tentativa(
        self, sequencial: int, retry_after_s: float | None
    ) -> datetime:
        """Espera progressiva com teto e dispersão, respeitando o retry_after do Telegram.

        `sequencial` já é a tentativa monotônica deste pedido (de
        `registrar_tentativa`); usá-lo como expoente evita persistir uma
        contagem separada só para o backoff. Ele conta toda tentativa do
        pedido, não só as que erraram por um `ErroDoTelegram` transitório — uma
        retentativa por contenção de ciclo antes do primeiro erro do Telegram já
        infla o expoente. Aceito de propósito: o teto (`TETO_DO_BACKOFF_S`)
        limita o efeito, e a alternativa exigiria persistir uma contagem à parte
        só para este cálculo.
        """
        if retry_after_s is not None:
            atraso = float(retry_after_s)
        else:
            # sequencial=1 (primeira tentativa) já é a primeira falha possível:
            # o expoente começa em zero para que o primeiro backoff seja
            # BASE_DO_BACKOFF_S, não o dobro.
            atraso = min(self.BASE_DO_BACKOFF_S * (2 ** (sequencial - 1)), self.TETO_DO_BACKOFF_S)
            atraso += random.uniform(0, atraso * self.PROPORCAO_DE_DISPERSAO)
        return self.relogio.agora() + timedelta(seconds=atraso)

    def _reagendar_apos_falha_transitoria(
        self, pedido: Pedido, motivo: str, sequencial: int, proximo: datetime
    ) -> Pedido:
        """Erro transitório do Telegram: mantém a reserva e tenta de novo mais tarde.

        Diferente de uma falha definitiva, nada é liberado nem consumido no
        ciclo aqui — a próxima tentativa reaproveita exatamente a mesma reserva
        (spec, 4.4; AC13).
        """
        reagendado = pedido.aguardar_tentativa(erro_sanitizado(motivo), proximo)
        self.repositorio.salvar(reagendado, sequencial)
        return reagendado

    def _marcar_incerto(
        self,
        pedido: Pedido,
        motivo: str,
        ciclo: Ciclo,
        versao_ciclo: int,
        sequencial: int,
    ) -> Pedido:
        incerto = pedido.marcar_incerto(motivo)
        self.repositorio.salvar(incerto, sequencial)
        if pedido.frase_reservada is not None:
            self._consumir_no_ciclo(ciclo, versao_ciclo, pedido.frase_reservada, com_ressalva=True)
        return incerto

    def _algum_destinatario_tem_incerteza(self, pedido: Pedido) -> bool:
        return any(
            self.repositorio.indices_incertos(pedido.identidade, destinatario)
            for destinatario in pedido.destinatarios
        )

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
        if self._algum_destinatario_tem_incerteza(pedido):
            return self._marcar_incerto(pedido, erro, ciclo, versao_ciclo, sequencial)
        encerrado = pedido.falhar(alguma_parte_enviada=alguma_enviada, motivo=erro)
        self.repositorio.salvar(encerrado, sequencial)
        if pedido.frase_reservada is not None:
            self._encerrar_no_ciclo(ciclo, versao_ciclo, pedido.frase_reservada, alguma_enviada)
        return encerrado
