from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import ClassVar, Protocol

from frase_diaria.aplicacao.diagnostico import erro_sanitizado
from frase_diaria.aplicacao.portas import Relogio
from frase_diaria.dominio.colecao import SnapshotPersistido, TentativaDeSincronizacao
from frase_diaria.dominio.pedido import (
    MOTIVO_ENVIO_INICIADO,
    MOTIVO_FRASE_RESERVADA,
    MOTIVO_PADRAO,
    MOTIVO_TODAS_AS_PARTES_CONFIRMADAS,
    EstadoDoPedido,
    Pedido,
)
from frase_diaria.dominio.status import (
    RelatorioDeStatus,
    SituacaoDaDiaria,
    SituacaoDaSincronizacao,
    UltimoEnvio,
)
from frase_diaria.dominio.tempo import dia_local, proxima_ocorrencia_diaria

# O motivo agregado pode identificar outros destinatários; a resposta usa categorias locais.
_MOTIVO_GENERICO_POR_ESTADO: dict[EstadoDoPedido, str] = {
    EstadoDoPedido.PENDENTE: MOTIVO_PADRAO,
    EstadoDoPedido.RESERVADO: MOTIVO_FRASE_RESERVADA,
    EstadoDoPedido.ENVIANDO: MOTIVO_ENVIO_INICIADO,
    EstadoDoPedido.AGUARDANDO_TENTATIVA: "aguardando nova tentativa",
    EstadoDoPedido.ENVIADO: MOTIVO_TODAS_AS_PARTES_CONFIRMADAS,
    EstadoDoPedido.PARCIAL: "nem todas as partes foram confirmadas",
    EstadoDoPedido.INCERTO: "intenção registrada sem confirmação; reenvio automático suspenso",
    EstadoDoPedido.FALHOU: "não foi possível confirmar a entrega",
    EstadoDoPedido.EXPIRADO: "janela de recuperação encerrada sem confirmar a entrega",
}


class RepositorioDePedidosStatus(Protocol):
    def obter(self, identidade: str) -> Pedido | None: ...
    def indices_confirmados(self, pedido: str, destinatario: int) -> set[int]: ...
    def indices_incertos(self, pedido: str, destinatario: int) -> set[int]: ...
    def ultimo_pedido_do_destinatario(self, destinatario: int, antes_de: date) -> Pedido | None: ...


@dataclass(frozen=True)
class _SituacaoDoDestinatario:
    """Pedido e situação já resolvida para quem consulta."""

    pedido: Pedido
    estado: EstadoDoPedido
    tem_incertas: bool


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

    ENTREGUE: ClassVar[frozenset[EstadoDoPedido]] = frozenset(
        {EstadoDoPedido.ENVIADO, EstadoDoPedido.PARCIAL, EstadoDoPedido.INCERTO}
    )

    def executar(self) -> RelatorioDeStatus:
        agora = self.relogio.agora()
        dia_hoje = dia_local(agora)
        pedido_hoje = self._diaria_de(dia_hoje)
        situacao_de_hoje = (
            self._situacao_do_destinatario(pedido_hoje) if pedido_hoje is not None else None
        )

        return RelatorioDeStatus(
            situacao_da_diaria_de_hoje=self._situacao(situacao_de_hoje),
            ultimo_envio=self._ultimo_envio(situacao_de_hoje, dia_hoje),
            proxima_ocorrencia_diaria=proxima_ocorrencia_diaria(
                agora,
                diaria_de_hoje_terminal=(
                    situacao_de_hoje is not None and situacao_de_hoje.estado.terminal
                ),
            ),
            sincronizacao=self._sincronizacao(),
        )

    def _situacao_do_destinatario(self, pedido: Pedido) -> _SituacaoDoDestinatario:
        estado, tem_incertas = self._estado_e_incertas_do_destinatario(pedido)
        return _SituacaoDoDestinatario(pedido=pedido, estado=estado, tem_incertas=tem_incertas)

    def _diaria_de(self, dia: date) -> Pedido | None:
        pedido = self.repositorio.obter(Pedido.identidade_de_diaria(dia))
        if pedido is not None and self.chat_id in pedido.destinatarios:
            return pedido
        # Históricos anteriores à v2 usam uma identidade diária por conversa.
        legado = self.repositorio.obter(f"diaria#{self.chat_id}#{dia.isoformat()}")
        if legado is not None and self.chat_id in legado.destinatarios:
            return legado
        return None

    def _situacao(self, situacao: _SituacaoDoDestinatario | None) -> SituacaoDaDiaria:
        if situacao is None:
            return SituacaoDaDiaria(
                existe=False, estado=None, motivo=None, tem_partes_incertas=False
            )
        return SituacaoDaDiaria(
            existe=True,
            estado=situacao.estado,
            motivo=self._motivo_seguro(situacao),
            tem_partes_incertas=situacao.tem_incertas,
        )

    def _motivo_seguro(self, situacao: _SituacaoDoDestinatario) -> str:
        if len(situacao.pedido.destinatarios) == 1 and situacao.estado is situacao.pedido.estado:
            motivo = erro_sanitizado(situacao.pedido.motivo_do_estado)
            if motivo and motivo != "erro de integração":
                return motivo
        return _MOTIVO_GENERICO_POR_ESTADO[situacao.estado]

    def _ultimo_envio(
        self, situacao_de_hoje: _SituacaoDoDestinatario | None, dia_hoje: date
    ) -> UltimoEnvio | None:
        if situacao_de_hoje is not None and situacao_de_hoje.estado in self.ENTREGUE:
            return UltimoEnvio(
                dia=dia_hoje,
                estado=situacao_de_hoje.estado,
                tem_partes_incertas=situacao_de_hoje.tem_incertas,
            )
        ultimo = self.repositorio.ultimo_pedido_do_destinatario(self.chat_id, dia_hoje)
        if ultimo is None:
            # Compatibilidade com diárias gravadas antes da criação do índice
            # por destinatário. As novas entregas deixam o histórico
            # consultável sem Scan; o dia anterior continua alcançável pelo
            # identificador determinístico durante a transição.
            ultimo = self._diaria_de(dia_hoje - timedelta(days=1))
        if ultimo is not None and self.chat_id in ultimo.destinatarios:
            situacao_anterior = self._situacao_do_destinatario(ultimo)
            dia = ultimo.dia_alvo_da_diaria()
            if dia is not None and situacao_anterior.estado in self.ENTREGUE:
                return UltimoEnvio(
                    dia=dia,
                    estado=situacao_anterior.estado,
                    tem_partes_incertas=situacao_anterior.tem_incertas,
                )
        return None

    def _estado_e_incertas_do_destinatario(self, pedido: Pedido) -> tuple[EstadoDoPedido, bool]:
        """Usa as confirmações próprias e o total previsto antes de consultar o agregado."""
        incertas = bool(self.repositorio.indices_incertos(pedido.identidade, self.chat_id))
        confirmadas = self.repositorio.indices_confirmados(pedido.identidade, self.chat_id)
        if (
            not incertas
            and pedido.total_de_partes is not None
            and pedido.total_de_partes > 0
            and set(range(pedido.total_de_partes)).issubset(confirmadas)
        ):
            return EstadoDoPedido.ENVIADO, False
        if incertas:
            return EstadoDoPedido.INCERTO, True
        # No formato individual antigo, o agregado já representa só esta conversa.
        if len(pedido.destinatarios) == 1 and pedido.total_de_partes is None:
            return pedido.estado, pedido.estado is EstadoDoPedido.INCERTO
        if self.chat_id in pedido.destinatarios_com_falha:
            return (EstadoDoPedido.PARCIAL if confirmadas else EstadoDoPedido.FALHOU), False
        if not pedido.estado.terminal:
            return pedido.estado, False
        if pedido.estado is EstadoDoPedido.ENVIADO:
            return pedido.estado, False
        if pedido.estado in (EstadoDoPedido.FALHOU, EstadoDoPedido.EXPIRADO):
            return pedido.estado, False
        # Só resta PARCIAL ou INCERTO agregados, por causa de OUTRO
        # destinatário — este aqui não tem incerta própria (já descartado
        # acima). Se recebeu algo, é parcial; se não recebeu nada, é falha.
        if confirmadas:
            return EstadoDoPedido.PARCIAL, False
        return EstadoDoPedido.FALHOU, False

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
    formatar: Callable[[RelatorioDeStatus], str]

    def executar(self) -> None:
        relatorio = self.consultar.executar()
        texto = self.formatar(relatorio)
        self.canal.enviar_texto(self.consultar.chat_id, texto)
