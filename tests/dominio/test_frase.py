"""Uma frase é uma entrega lógica que pode ocupar várias mensagens.

A divisão inteligente de texto longo é do ticket 12; aqui interessa apenas que a
frase saiba se apresentar como uma sequência ordenada de partes, porque é essa
sequência que a persistência acompanha parte a parte.
"""

import pytest

from frase_diaria.dominio.frase import Frase


def test_frase_simples_tem_uma_parte() -> None:
    frase = Frase(identidade="bloco-1", partes=("Feito é melhor que perfeito.",))

    assert frase.partes == ("Feito é melhor que perfeito.",)
    assert frase.quantidade_de_partes == 1


def test_frase_pode_ocupar_varias_partes_em_ordem() -> None:
    frase = Frase(identidade="bloco-2", partes=("primeira", "segunda", "terceira"))

    assert frase.quantidade_de_partes == 3
    assert frase.partes[0] == "primeira"
    assert frase.partes[2] == "terceira"


def test_frase_sem_partes_nao_e_entregavel() -> None:
    with pytest.raises(ValueError, match="ao menos uma parte"):
        Frase(identidade="bloco-3", partes=())


def test_parte_vazia_nao_e_entregavel() -> None:
    # Uma parte em branco viraria uma mensagem vazia no Telegram, que a Bot API
    # recusa — melhor falhar aqui, onde o diagnóstico é claro.
    with pytest.raises(ValueError, match="parte vazia"):
        Frase(identidade="bloco-4", partes=("texto", "   "))


def test_a_identidade_e_obrigatoria() -> None:
    with pytest.raises(ValueError, match="identidade"):
        Frase(identidade="", partes=("texto",))


def test_frases_com_a_mesma_identidade_sao_iguais() -> None:
    # A identidade é o id do bloco raiz; texto igual nunca serve como critério.
    uma = Frase(identidade="bloco-5", partes=("texto original",))
    outra = Frase(identidade="bloco-5", partes=("texto editado",))

    assert uma.identidade == outra.identidade
