from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

FUSO_LOCAL = ZoneInfo("America/Sao_Paulo")

# A janela de recuperação vai do envio-alvo ao meio-dia local do mesmo dia
# (spec, 4.5). Vivem juntas aqui porque são os dois extremos da mesma janela;
# separá-las por camada fragmentaria um conceito só.
INICIO_DO_ENVIO_ALVO_LOCAL = time(8, 0)
LIMITE_DE_RECUPERACAO_LOCAL = time(12, 0)


def em_utc(instante: datetime) -> datetime:
    """Normaliza um instante; datas sem fuso são ambíguas e recusadas."""
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ValueError("instante precisa declarar o fuso")
    return instante.astimezone(UTC)


def dia_local(instante: datetime) -> date:
    """Converte um instante em UTC no dia do calendário local da usuária.

    Instantes são gravados em UTC, mas a chave diária de um pedido é o dia local:
    às 23h de São Paulo já é o dia seguinte em UTC, e usar o dia UTC criaria duas
    diárias para a mesma data local.
    """
    if instante.tzinfo is None:
        raise ValueError("instante precisa declarar o fuso; grave instantes em UTC")
    return instante.astimezone(FUSO_LOCAL).date()


def _meio_dia_local_em_utc(dia: date) -> datetime:
    return em_utc(datetime.combine(dia, LIMITE_DE_RECUPERACAO_LOCAL, tzinfo=FUSO_LOCAL))


def _envio_alvo_local_em_utc(dia: date) -> datetime:
    return em_utc(datetime.combine(dia, INICIO_DO_ENVIO_ALVO_LOCAL, tzinfo=FUSO_LOCAL))


def proxima_ocorrencia_diaria(agora: datetime, diaria_de_hoje_terminal: bool) -> datetime:
    """O próximo 08:00 local que /status deve anunciar como "próxima ocorrência".

    Enquanto a diária de hoje não chegou a um estado terminal — ainda não foi
    criada, está pendente, ou está em retentativa —, ela continua sendo "a"
    ocorrência corrente, mesmo que 08:00 já tenha passado: é para ela que o
    reconciliador ainda está trabalhando. Só depois de terminada (com sucesso
    ou definitivamente) é que a próxima ocorrência passa a ser amanhã.
    """
    dia = dia_local(agora)
    if not diaria_de_hoje_terminal:
        return _envio_alvo_local_em_utc(dia)
    return _envio_alvo_local_em_utc(dia + timedelta(days=1))


def prazo_da_diaria(dia_alvo: date) -> datetime:
    """O instante, em UTC, em que a diária do dia local `dia_alvo` deve ser abandonada.

    Meio-dia local: depois disso nenhuma nova chamada ao Telegram é iniciada, e a
    diária pendente — inclusive parcial — é encerrada com o resultado conservado
    (spec, 4.5; AC14).
    """
    return _meio_dia_local_em_utc(dia_alvo)


@dataclass(frozen=True)
class PoliticaDeExtra:
    """Como um extra pode ser retentado, decidido uma única vez na criação.

    `prazo=None` com `tentativa_unica=True` não significa "sem limite": significa
    que não há retentativa alguma, então nenhum prazo de retentativa se aplica —
    a única tentativa acontece sempre que for despachada, cedo ou tarde, e uma
    falha nela (transitória ou não) encerra o pedido (spec, 4.5). Um prazo datado
    não serviria aqui: o despacho é sempre um pouco posterior à criação, e
    qualquer prazo próximo da criação seria ultrapassado antes da primeira
    tentativa rodar — o que negaria a tentativa que a política promete.
    """

    prazo: datetime | None
    tentativa_unica: bool


def politica_do_extra(criado_em: datetime) -> PoliticaDeExtra:
    """Decide a política de retentativa de um extra a partir do instante de criação.

    Criado antes do meio-dia local: retenta até o meio-dia do mesmo dia local.
    Criado a partir do meio-dia: uma única tentativa imediata, sem fila para o
    dia seguinte — política decidida pela usuária (spec, 4.5).
    """
    limite = _meio_dia_local_em_utc(dia_local(criado_em))
    if criado_em < limite:
        return PoliticaDeExtra(prazo=limite, tentativa_unica=False)
    return PoliticaDeExtra(prazo=None, tentativa_unica=True)
