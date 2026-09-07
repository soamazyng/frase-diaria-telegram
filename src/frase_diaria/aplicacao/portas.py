from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from frase_diaria.dominio.pedido import Pedido


class CriadorDePedidos(Protocol):
    def criar_se_ausente(self, pedido: Pedido, instante: datetime) -> bool: ...


class Relogio(Protocol):
    """Fonte do tempo. Substituível nos testes para exercitar a janela de envio."""

    def agora(self) -> datetime:
        """Instante atual, sempre com fuso declarado (UTC em produção)."""
        ...


class Sorteio(Protocol):
    """Gerador aleatório. Substituível nos testes para tornar a seleção determinística."""

    def escolher[T](self, candidatos: Sequence[T]) -> T:
        """Escolhe um entre os candidatos. Recebe sequência não vazia."""
        ...
