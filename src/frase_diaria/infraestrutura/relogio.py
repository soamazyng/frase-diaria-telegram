from datetime import UTC, datetime


class RelogioDoSistema:
    """Relógio de produção. Sempre em UTC — a conversão para o dia local é do domínio."""

    def agora(self) -> datetime:
        return datetime.now(UTC)
