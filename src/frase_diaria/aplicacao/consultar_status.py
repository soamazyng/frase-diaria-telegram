from dataclasses import dataclass
from datetime import date, timedelta
from typing import ClassVar, Protocol

from frase_diaria.aplicacao.portas import Relogio
from frase_diaria.dominio.colecao import SnapshotPersistido, TentativaDeSincronizacao
from frase_diaria.dominio.pedido import EstadoDoPedido, Pedido
from frase_diaria.dominio.status import (
    RelatorioDeStatus,
    SituacaoDaDiaria,
    SituacaoDaSincronizacao,
    UltimoEnvio,
)
from frase_diaria.dominio.tempo import dia_local, proxima_ocorrencia_diaria
from frase_diaria.telegram.status import formatar_status


class RepositorioDePedidosStatus(Protocol):
    def obter(self, identidade: str) -> Pedido | None: ...
    def indices_incertos(self, pedido: str, destinatario: int) -> set[int]: ...


class RepositorioDeColecaoStatus(Protocol):
    """Só leitura: `/status` nunca sincroniza — lê o que a última sincronização
    real (diária, extra ou reconciliador) já deixou persistido."""

    def carregar_ativa(self) -> SnapshotPersistido | None: ...
    def ultima_tentativa(self) -> TentativaDeSincronizacao | None: ...


@dataclass(frozen=True)
class ConsultarStatus:
    """Monta o retrato de `/status` sem consumir frase, tocar o ciclo ou sincronizar.

    Não recebe `ciclos` nem `reserva`: nada aqui pode chamá-los, por
    construção. Os dados de sincronização vêm de uma leitura (`colecao`), não
    de uma chamada ao Notion — disparar uma sincronização nova só para
    responder a uma consulta seria trabalho e custo que a usuária não pediu, e
    apagaria a última falha real assim que a nova tentativa desse certo.
    """

    repositorio: RepositorioDePedidosStatus
    colecao: RepositorioDeColecaoStatus
    relogio: Relogio
    chat_id: int

    # Estados em que algo de fato chegou à usuária — mesmo que com ressalva.
    ENTREGUE: ClassVar[frozenset[EstadoDoPedido]] = frozenset(
        {EstadoDoPedido.ENVIADO, EstadoDoPedido.PARCIAL, EstadoDoPedido.INCERTO}
    )

    def executar(self) -> RelatorioDeStatus:
        agora = self.relogio.agora()
        dia_hoje = dia_local(agora)
        pedido_hoje = self._diaria_de(dia_hoje)

        return RelatorioDeStatus(
            situacao_da_diaria_de_hoje=self._situacao(pedido_hoje),
            ultimo_envio=self._ultimo_envio(pedido_hoje, dia_hoje),
            proxima_ocorrencia_diaria=proxima_ocorrencia_diaria(
                agora,
                diaria_de_hoje_terminal=pedido_hoje is not None and pedido_hoje.estado.terminal,
            ),
            sincronizacao=self._sincronizacao(),
        )

    def _diaria_de(self, dia: date) -> Pedido | None:
        # v2: um único pedido diário para todos os destinatários — a busca não
        # é mais por chat_id, mas o "incerto" abaixo continua sendo o do
        # destinatário que perguntou (self.chat_id), não um agregado de todos.
        pedido = self.repositorio.obter(Pedido.identidade_de_diaria(dia))
        if pedido is not None:
            return pedido
        # Transição (achado do code-review): no dia em que a v2 é publicada, a
        # diária de ONTEM ainda está gravada no formato anterior à v2
        # (`diaria#<chat_id>#<dia>`), que este destinatário já usava. Sem este
        # fallback, `/status` relataria "nunca enviado" para um dia que na
        # verdade entregou — um só dia de imprecisão de leitura, não de dado
        # perdido. Pode ser removido depois que essa janela de transição passar.
        return self.repositorio.obter(f"diaria#{self.chat_id}#{dia.isoformat()}")

    def _situacao(self, pedido: Pedido | None) -> SituacaoDaDiaria:
        if pedido is None:
            return SituacaoDaDiaria(
                existe=False, estado=None, motivo=None, tem_partes_incertas=False
            )
        return SituacaoDaDiaria(
            existe=True,
            estado=pedido.estado,
            motivo=pedido.motivo_do_estado,
            tem_partes_incertas=bool(
                self.repositorio.indices_incertos(pedido.identidade, self.chat_id)
            ),
        )

    def _ultimo_envio(self, pedido_hoje: Pedido | None, dia_hoje: date) -> UltimoEnvio | None:
        if pedido_hoje is not None and pedido_hoje.estado in self.ENTREGUE:
            return self._como_ultimo_envio(pedido_hoje, dia_hoje)
        # Sem índice por chat_id no schema, "último envio" alcança só hoje e
        # ontem — as duas identidades diárias que dá para consultar sem
        # varrer o histórico (spec, 4.8: "índice de pendências... sem varrer
        # o histórico" é o mesmo princípio aplicado aqui).
        ontem = dia_hoje - timedelta(days=1)
        pedido_ontem = self._diaria_de(ontem)
        if pedido_ontem is not None and pedido_ontem.estado in self.ENTREGUE:
            return self._como_ultimo_envio(pedido_ontem, ontem)
        return None

    def _como_ultimo_envio(self, pedido: Pedido, dia: date) -> UltimoEnvio:
        return UltimoEnvio(
            dia=dia,
            estado=pedido.estado,
            tem_partes_incertas=bool(
                self.repositorio.indices_incertos(pedido.identidade, self.chat_id)
            ),
        )

    def _sincronizacao(self) -> SituacaoDaSincronizacao:
        ativa = self.colecao.carregar_ativa()
        tentativa = self.colecao.ultima_tentativa()

        if ativa is None:
            return SituacaoDaSincronizacao(
                colecao_disponivel=False,
                usou_cache=False,
                instante_da_ultima_valida=None,
                instante_da_ultima_tentativa=tentativa.instante if tentativa else None,
                erro=tentativa.erro if tentativa else None,
            )
        # Uma tentativa recente com erro não produziu snapshot novo — o que
        # está ativo é, necessariamente, o cache de uma sincronização anterior.
        usando_cache = tentativa is not None and tentativa.erro is not None
        return SituacaoDaSincronizacao(
            colecao_disponivel=True,
            usou_cache=usando_cache,
            instante_da_ultima_valida=ativa.instante,
            instante_da_ultima_tentativa=tentativa.instante if tentativa else ativa.instante,
            erro=tentativa.erro if tentativa else None,
        )


class CanalDeEnvioTexto(Protocol):
    def enviar_texto(self, chat_id: int, texto: str) -> int: ...


@dataclass(frozen=True)
class EnviarStatus:
    """Consulta, formata e envia o relatório de `/status` — o que o worker faz.

    Falhar aqui propaga: a Lambda foi invocada assincronamente, e deixar a
    exceção subir é o que aciona a reentrega nativa dela. Diferente de um
    pedido, `/status` não tem identidade nem confirmação persistida — reenviar
    a mesma resposta informativa não duplica nada que importe.
    """

    consultar: ConsultarStatus
    canal: CanalDeEnvioTexto

    def executar(self) -> None:
        relatorio = self.consultar.executar()
        texto = formatar_status(relatorio)
        self.canal.enviar_texto(self.consultar.chat_id, texto)
