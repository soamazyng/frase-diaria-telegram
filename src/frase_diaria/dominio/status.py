from dataclasses import dataclass
from datetime import date, datetime

from frase_diaria.dominio.pedido import EstadoDoPedido


@dataclass(frozen=True)
class SituacaoDaDiaria:
    """O que se sabe sobre a diária de um dia específico, sem decidir texto algum."""

    existe: bool
    estado: EstadoDoPedido | None
    motivo: str | None
    tem_partes_incertas: bool


@dataclass(frozen=True)
class UltimoEnvio:
    """A entrega diária confirmada mais recente encontrada (spec, 4.7)."""

    dia: date
    estado: EstadoDoPedido
    tem_partes_incertas: bool


@dataclass(frozen=True)
class SituacaoDaSincronizacao:
    """O que a última sincronização real (não uma nova, disparada por `/status`) deixou.

    `instante_da_ultima_valida` é `None` só quando `colecao_disponivel` é
    `False` — nenhum snapshot, novo ou em cache, está disponível (AC09).
    `instante_da_ultima_tentativa` é `None` só antes de qualquer sincronização
    ter rodado.
    """

    colecao_disponivel: bool
    usou_cache: bool
    instante_da_ultima_valida: datetime | None
    instante_da_ultima_tentativa: datetime | None
    erro: str | None


@dataclass(frozen=True)
class RelatorioDeStatus:
    """Os dados brutos de `/status`, sem formatação — a apresentação é do adaptador Telegram."""

    situacao_da_diaria_de_hoje: SituacaoDaDiaria
    ultimo_envio: UltimoEnvio | None
    proxima_ocorrencia_diaria: datetime
    sincronizacao: SituacaoDaSincronizacao
