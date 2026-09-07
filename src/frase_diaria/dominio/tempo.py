from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

FUSO_LOCAL = ZoneInfo("America/Sao_Paulo")


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
