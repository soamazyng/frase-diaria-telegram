"""A coleção válida é o snapshot completo e validado da fonte (vocabulário da spec).

Estes testes cobrem só o modelo — identidade obrigatória, ao menos um bloco — e
a distinção entre "coleção vazia legítima" e "leitura que não pôde concluir",
que é o que impede uma sincronização parcial de virar exclusão em massa (AC08).
"""

import pytest

from frase_diaria.dominio.colecao import (
    ColecaoValida,
    Diagnostico,
    FrasePreservada,
    SincronizacaoIncompleta,
)
from frase_diaria.dominio.conteudo import Bloco, Trecho

UM_BLOCO = (Bloco(tipo="numbered_list_item", trechos=(Trecho(texto="uma frase"),)),)


def test_frase_preservada_precisa_de_identidade() -> None:
    with pytest.raises(ValueError, match="identidade"):
        FrasePreservada(identidade="", blocos=UM_BLOCO)


def test_frase_preservada_precisa_de_ao_menos_um_bloco() -> None:
    with pytest.raises(ValueError, match="bloco"):
        FrasePreservada(identidade="bloco-1", blocos=())


def test_frase_preservada_pode_nao_ter_discussoes() -> None:
    frase = FrasePreservada(identidade="bloco-1", blocos=UM_BLOCO)

    assert frase.discussoes == ()


def test_colecao_vazia_e_legitima_e_nao_e_um_erro() -> None:
    # Uma leitura completa sem frases substitui a coleção por um snapshot vazio
    # — não ressuscita itens excluídos (spec, 4.2).
    vazia = ColecaoValida(itens=())

    assert vazia.itens == ()


def test_colecao_carrega_diagnosticos_sem_impedir_a_sincronizacao() -> None:
    diagnostico = Diagnostico(categoria="conteudo_solto", descricao="bloco x fora de qualquer item")
    colecao = ColecaoValida(itens=(FrasePreservada(identidade="bloco-1", blocos=UM_BLOCO),))
    colecao = ColecaoValida(itens=colecao.itens, diagnosticos=(diagnostico,))

    assert colecao.diagnosticos == (diagnostico,)
    assert len(colecao.itens) == 1


def test_sincronizacao_incompleta_e_uma_excecao_distinguivel() -> None:
    # Erro de autorização, timeout ou paginação incompleta viram este tipo —
    # nunca um snapshot vazio, que apagaria o histórico de exclusões (AC08).
    with pytest.raises(SincronizacaoIncompleta, match="timeout"):
        raise SincronizacaoIncompleta("timeout ao buscar filhos")
