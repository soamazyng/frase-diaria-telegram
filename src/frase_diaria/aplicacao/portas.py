from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from frase_diaria.dominio.colecao import ColecaoValida, SnapshotPersistido
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


class ConflitoDeConcorrencia(RuntimeError):
    """Uma escrita condicional perdeu a corrida: outro executor já avançou o estado.

    Cobre tanto a versão do ciclo quanto o lease de um pedido — nos dois casos, a
    escrita foi recusada porque o que estava em memória já não é o que está
    persistido, e sobrescrever corromperia o estado (spec, 4.9).
    """


class FonteDaColecao(Protocol):
    """Lê a coleção completa e validada da fonte externa (Notion)."""

    def ler(self, pagina_id: str) -> ColecaoValida:
        """Levanta `SincronizacaoIncompleta` numa leitura parcial ou com erro."""
        ...


class RepositorioDeColecao(Protocol):
    """O snapshot ativo da coleção — o que sobra quando a fonte está fora do ar."""

    def carregar_ativa(self) -> SnapshotPersistido | None: ...
    def substituir(self, colecao: ColecaoValida, instante: datetime) -> None:
        """Publica um novo snapshot ativo, inclusive um legitimamente vazio."""
        ...
