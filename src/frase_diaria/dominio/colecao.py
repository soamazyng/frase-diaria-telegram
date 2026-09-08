from dataclasses import dataclass
from datetime import datetime

from frase_diaria.dominio.conteudo import Bloco


@dataclass(frozen=True)
class FrasePreservada:
    """Uma frase tal como preservada da fonte, antes de qualquer renderização.

    `identidade` é o id do bloco raiz — estável a mover ou editar; apagar e
    recriar o bloco cria outra identidade, e igualdade de texto nunca serve
    como critério de deduplicação (spec, 4.2).
    """

    identidade: str
    blocos: tuple[Bloco, ...]
    discussoes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.identidade.strip():
            raise ValueError("frase preservada precisa de identidade")
        if not self.blocos:
            raise ValueError("frase preservada precisa de ao menos um bloco")


@dataclass(frozen=True)
class Diagnostico:
    """Um evento que não impede a sincronização, mas precisa ficar visível.

    Cobre conteúdo solto de associação ambígua e limitação de acesso a
    discussões nativas — nunca uma atribuição inventada (spec, 4.2).
    """

    categoria: str
    descricao: str


@dataclass(frozen=True)
class ColecaoValida:
    """Snapshot completo e validado da fonte, inclusive um snapshot legitimamente vazio.

    Só existe depois de uma leitura concluída e validada; uma leitura parcial
    vira `SincronizacaoIncompleta` em vez de uma coleção com menos itens.
    """

    itens: tuple[FrasePreservada, ...]
    diagnosticos: tuple[Diagnostico, ...] = ()


@dataclass(frozen=True)
class SnapshotPersistido:
    """O que sobrevive de uma sincronização: identificador, instante e a coleção.

    `identificador` correlaciona este snapshot em diagnósticos e no futuro
    `/status` (ticket 15) — não participa de nenhuma decisão de negócio.
    """

    identificador: str
    colecao: ColecaoValida
    instante: datetime


class SincronizacaoIncompleta(RuntimeError):
    """Leitura paginada incompleta, erro de autorização ou timeout.

    Nunca deve ser interpretada como exclusão em massa: quem recebe isto
    conserva o snapshot anterior (spec, 4.2; AC08).
    """


@dataclass(frozen=True)
class TentativaDeSincronizacao:
    """O resultado da tentativa de sincronização mais recente, sucesso ou não.

    Distinto de `SnapshotPersistido`: uma tentativa que falhou não produz um
    snapshot novo, mas ainda precisa ficar visível — é o que `/status` relata
    como "última tentativa" e "falha ativa" (spec, 4.7/4.8), sem depender de
    disparar uma sincronização nova só para responder à consulta.
    """

    instante: datetime
    erro: str | None
