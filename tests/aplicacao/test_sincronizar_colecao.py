"""Sincronizar a coleção decide entre publicar o que leu ou usar o cache.

Notion indisponível usa a última coleção válida e indica uso de cache, data e
erro da sincronização; sem cache disponível, registra falha (AC09). Uma
leitura bem-sucedida — mesmo legitimamente vazia — sempre substitui o
snapshot persistido, nunca ressuscitando frases excluídas.
"""

from datetime import UTC, datetime

import pytest

from frase_diaria.aplicacao.sincronizar_colecao import SincronizarColecao
from frase_diaria.dominio.colecao import ColecaoValida, FrasePreservada, SnapshotPersistido
from frase_diaria.dominio.colecao import SincronizacaoIncompleta as ErroDeSincronizacao
from frase_diaria.dominio.conteudo import Bloco, Trecho

AGORA = datetime(2026, 9, 7, 8, 0, tzinfo=UTC)
ANTES = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)
PAGINA = "pagina-colecao"


def _frase(identidade: str) -> FrasePreservada:
    return FrasePreservada(
        identidade=identidade,
        blocos=(Bloco(tipo="numbered_list_item", trechos=(Trecho(texto=identidade),)),),
    )


class RelogioFixo:
    def agora(self) -> datetime:
        return AGORA


class LeitorFalso:
    def __init__(self, resultado: ColecaoValida | Exception) -> None:
        self.resultado = resultado
        self.chamadas: list[str] = []

    def ler(self, pagina_id: str) -> ColecaoValida:
        self.chamadas.append(pagina_id)
        if isinstance(self.resultado, Exception):
            raise self.resultado
        return self.resultado


class RepositorioFalso:
    def __init__(self, snapshot: SnapshotPersistido | None = None) -> None:
        self.snapshot = snapshot
        self.substituicoes: list[ColecaoValida] = []

    def carregar_ativa(self) -> SnapshotPersistido | None:
        return self.snapshot

    def substituir(self, colecao: ColecaoValida, instante: datetime) -> None:
        self.substituicoes.append(colecao)
        self.snapshot = SnapshotPersistido(
            identificador="ignorado", colecao=colecao, instante=instante
        )


def test_sincronizacao_bem_sucedida_persiste_e_nao_usa_cache() -> None:
    colecao = ColecaoValida(itens=(_frase("b1"),))
    repositorio = RepositorioFalso()
    caso = SincronizarColecao(
        leitor=LeitorFalso(colecao),
        repositorio=repositorio,
        pagina_id=PAGINA,
        relogio=RelogioFixo(),
    )

    resultado = caso.executar()

    assert resultado.colecao is colecao
    assert resultado.usou_cache is False
    assert resultado.instante_do_snapshot == AGORA
    assert resultado.erro_da_sincronizacao is None
    assert repositorio.substituicoes == [colecao]


def test_colecao_legitimamente_vazia_tambem_substitui_o_cache() -> None:
    # Leitura completa sem frases não pode continuar servindo as antigas.
    anterior = SnapshotPersistido(
        identificador="snap-1", colecao=ColecaoValida(itens=(_frase("velha"),)), instante=ANTES
    )
    repositorio = RepositorioFalso(anterior)
    caso = SincronizarColecao(
        leitor=LeitorFalso(ColecaoValida(itens=())),
        repositorio=repositorio,
        pagina_id=PAGINA,
        relogio=RelogioFixo(),
    )

    resultado = caso.executar()

    assert resultado.colecao.itens == ()
    assert resultado.usou_cache is False
    assert repositorio.snapshot is not None
    assert repositorio.snapshot.colecao.itens == ()


def test_notion_indisponivel_com_cache_usa_o_snapshot_anterior() -> None:
    anterior = SnapshotPersistido(
        identificador="snap-1", colecao=ColecaoValida(itens=(_frase("b1"),)), instante=ANTES
    )
    repositorio = RepositorioFalso(anterior)
    caso = SincronizarColecao(
        leitor=LeitorFalso(ErroDeSincronizacao("Notion respondeu HTTP 504")),
        repositorio=repositorio,
        pagina_id=PAGINA,
        relogio=RelogioFixo(),
    )

    resultado = caso.executar()

    assert resultado.colecao is anterior.colecao
    assert resultado.usou_cache is True
    assert resultado.instante_do_snapshot == ANTES
    assert resultado.erro_da_sincronizacao == "Notion respondeu HTTP 504"
    assert repositorio.substituicoes == []


def test_notion_indisponivel_sem_cache_registra_falha() -> None:
    repositorio = RepositorioFalso(None)
    caso = SincronizarColecao(
        leitor=LeitorFalso(ErroDeSincronizacao("Notion respondeu HTTP 504")),
        repositorio=repositorio,
        pagina_id=PAGINA,
        relogio=RelogioFixo(),
    )

    with pytest.raises(ErroDeSincronizacao):
        caso.executar()
