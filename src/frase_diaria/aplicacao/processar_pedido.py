import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from frase_diaria.aplicacao.portas import Relogio, Sorteio
from frase_diaria.dominio.ciclo import Ciclo
from frase_diaria.dominio.frase import Frase
from frase_diaria.dominio.pedido import Pedido
from frase_diaria.dominio.selecao import SemFrase, selecionar
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


class RepositorioDeCiclos(Protocol):
    def carregar(self) -> Ciclo: ...
    def salvar(self, ciclo: Ciclo) -> None: ...


class Reserva(Protocol):
    def efetivar(self, pedido: Pedido, ciclo: Ciclo) -> None:
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
    """

    repositorio: RepositorioDePedidos
    fonte: FonteDeFrases
    canal: CanalDeEnvio
    sorteio: Sorteio
    relogio: Relogio
    ciclos: RepositorioDeCiclos
    reserva: Reserva

    def executar(self, identidade: str) -> Pedido | None:
        pedido = self.repositorio.obter(identidade)
        if pedido is None:
            _log.warning("pedido %s não encontrado", identidade)
            return None
        if pedido.estado.terminal:
            # Estado terminal não reabre: um disparo duplicado não reenvia.
            return pedido

        ciclo = self.ciclos.carregar()
        escolha = self._escolher(pedido, ciclo)

        if escolha is SemFrase.AGUARDANDO_RESERVA:
            # Transitório: outro pedido segura a última frase livre. Encerrar
            # aqui levaria o pedido a estado terminal, de onde nem a retomada nem
            # a janela de recuperação o tirariam.
            self.repositorio.registrar_tentativa(
                identidade, "aguardando", "todas as frases reservadas", self.relogio.agora()
            )
            raise ReservaPendente(f"sem frase livre para {identidade}; tentar de novo")
        if escolha is SemFrase.COLECAO_VAZIA:
            return self._encerrar_sem_conteudo(pedido, ciclo)

        frase, ciclo = escolha
        if pedido.frase_reservada is None:
            # Ciclo e pedido em uma transação: gravar um sem o outro deixaria uma
            # reserva órfã que nada libera, travando o ciclo para sempre.
            pedido = pedido.reservar(frase.identidade)
            self.reserva.efetivar(pedido, ciclo)

        return self._entregar(pedido, frase, ciclo)

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

    def _encerrar_sem_conteudo(self, pedido: Pedido, ciclo: Ciclo) -> Pedido:
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
        # Pedido primeiro: um crash depois disto deixa o ciclo desatualizado, que
        # é recuperável; a ordem inversa deixaria o pedido reivindicando uma
        # reserva que o ciclo já soltou, e a retomada reentregaria a frase.
        self.repositorio.salvar(encerrado)
        if pedido.frase_reservada is not None:
            self._encerrar_no_ciclo(ciclo, pedido.frase_reservada, ja_entregou)
        self.repositorio.registrar_tentativa(pedido.identidade, "falhou", motivo, agora)
        return encerrado

    def _encerrar_no_ciclo(self, ciclo: Ciclo, frase: str, alguma_enviada: bool) -> None:
        """Consumo só depois de entrega confirmada.

        Nada entregue devolve a frase às elegíveis. Entrega parcial marca consumo
        **com ressalva**: a frase conta como gasta, para não reenviar
        automaticamente algo que já pode ter chegado, e a dúvida fica registrada.
        """
        if alguma_enviada:
            self._consumir_no_ciclo(ciclo, frase, com_ressalva=True)
        elif frase in ciclo.reservadas:
            self.ciclos.salvar(ciclo.liberar(frase))

    def _consumir_no_ciclo(self, ciclo: Ciclo, frase: str, com_ressalva: bool) -> None:
        """Marca a frase como gasta, mesmo que o ciclo tenha perdido a reserva.

        Perder a reserva é sinal de divergência — uma gravação concorrente
        sobrescreveu o ciclo, por exemplo. Pular o consumo em silêncio deixaria
        uma frase já entregue elegível de novo no mesmo ciclo, quebrando o
        sorteio sem repetição. Registrar e consumir mesmo assim é o desfecho
        correto: a mensagem foi para a usuária.
        """
        if ciclo.foi_consumida(frase):
            return
        if frase not in ciclo.reservadas:
            _log.warning("ciclo perdeu a reserva de %s; consumindo assim mesmo", frase)
            ciclo = ciclo.reservar(frase)
        self.ciclos.salvar(ciclo.consumir(frase, com_ressalva=com_ressalva))

    def _entregar(self, pedido: Pedido, frase: Frase, ciclo: Ciclo) -> Pedido:
        ja_confirmadas = self.repositorio.indices_confirmados(pedido.identidade)
        alguma_enviada = bool(ja_confirmadas)

        for indice, texto in enumerate(frase.partes):
            if indice in ja_confirmadas:
                continue
            try:
                message_id = self.canal.enviar_texto(pedido.chat_id, texto)
            except ErroDoTelegram as erro:
                # A mensagem já vem sanitizada do canal: sem token, sem URL.
                return self._encerrar_com_falha(pedido, str(erro), alguma_enviada, ciclo)
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
        # Consumo definitivo: todas as partes confirmadas.
        self._consumir_no_ciclo(ciclo, frase.identidade, com_ressalva=False)
        self.repositorio.registrar_tentativa(
            pedido.identidade, "enviado", None, self.relogio.agora()
        )
        return concluido

    def _encerrar_com_falha(
        self, pedido: Pedido, erro: str, alguma_enviada: bool, ciclo: Ciclo
    ) -> Pedido:
        encerrado = pedido.falhar(alguma_parte_enviada=alguma_enviada)
        self.repositorio.salvar(encerrado)
        if pedido.frase_reservada is not None:
            self._encerrar_no_ciclo(ciclo, pedido.frase_reservada, alguma_enviada)
        self.repositorio.registrar_tentativa(
            pedido.identidade, "falhou", erro, self.relogio.agora()
        )
        return encerrado
