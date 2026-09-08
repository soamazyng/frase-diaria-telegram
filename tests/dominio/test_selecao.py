"""Sortear a próxima frase, respeitando o ciclo.

Concentra as duas regras que o AC04 e o AC05 cobram: percorrer a coleção inteira
sem repetir, e não começar o ciclo seguinte pela frase que acabou de sair.
"""

from typing import Any

from frase_diaria.dominio.ciclo import Ciclo
from frase_diaria.dominio.selecao import SemFrase, selecionar

TODAS = ("a", "b", "c")


class SorteioDeterminista:
    """Escolhe sempre o primeiro candidato: torna a sequência verificável."""

    def escolher(self, candidatos: Any) -> Any:
        return candidatos[0]


class SorteioDoUltimo:
    def escolher(self, candidatos: Any) -> Any:
        return candidatos[-1]


def _escolher(ciclo: Ciclo, sorteio: Any = None) -> tuple[str, Ciclo]:
    """Seleciona exigindo que haja frase: falha alto se não houver."""
    resultado = selecionar(ciclo, TODAS, sorteio or SorteioDeterminista())
    assert not isinstance(resultado, SemFrase), resultado
    return resultado


def test_seleciona_e_reserva_em_um_passo() -> None:
    escolhida, ciclo = _escolher(Ciclo.primeiro())

    assert escolhida == "a"
    assert ciclo.elegiveis(TODAS) == ("b", "c")


# --- AC04 --------------------------------------------------------------------


def test_n_entregas_no_ciclo_tem_identidades_distintas() -> None:
    ciclo = Ciclo.primeiro()
    entregues = []

    for _ in range(len(TODAS)):
        escolhida, ciclo = _escolher(ciclo)
        entregues.append(escolhida)
        ciclo = ciclo.consumir(escolhida)

    assert sorted(entregues) == sorted(TODAS)
    assert len(set(entregues)) == len(TODAS)


def test_ciclo_esgotado_reinicia_sozinho_na_proxima_selecao() -> None:
    ciclo = Ciclo.primeiro()
    for _ in range(len(TODAS)):
        escolhida, ciclo = _escolher(ciclo)
        ciclo = ciclo.consumir(escolhida)

    escolhida, novo = _escolher(ciclo)

    assert novo.numero == 2
    assert escolhida in TODAS


# --- AC05 --------------------------------------------------------------------


def test_a_primeira_do_novo_ciclo_difere_da_ultima_entregue() -> None:
    # O sorteio escolhe sempre o último candidato; sem a regra, "c" — a última
    # entregue — sairia de novo em seguida.
    ciclo = Ciclo.primeiro()
    for _ in range(len(TODAS)):
        escolhida, ciclo = _escolher(ciclo, SorteioDoUltimo())
        ciclo = ciclo.consumir(escolhida)
    assert ciclo.ultima_entregue == "a"

    primeira_do_novo, _ = _escolher(ciclo, SorteioDoUltimo())

    assert primeira_do_novo != "a"


def test_com_uma_unica_frase_a_repeticao_acontece() -> None:
    uma = ("solitaria",)
    primeira = selecionar(Ciclo.primeiro(), uma, SorteioDeterminista())
    assert not isinstance(primeira, SemFrase)
    escolhida, ciclo = primeira
    ciclo = ciclo.consumir(escolhida)

    segunda = selecionar(ciclo, uma, SorteioDeterminista())
    assert not isinstance(segunda, SemFrase)
    de_novo, _ = segunda

    assert de_novo == "solitaria"


def test_reserva_pendente_impede_reinicio_e_deixa_sem_candidata() -> None:
    # Todas consumidas menos uma, que está reservada por outro pedido: não há o
    # que sortear, e reiniciar duplicaria a frase reservada no ciclo novo.
    ciclo = Ciclo.primeiro()
    for _ in range(2):
        escolhida, ciclo = _escolher(ciclo)
        ciclo = ciclo.consumir(escolhida)
    _, ciclo = _escolher(ciclo)

    assert selecionar(ciclo, TODAS, SorteioDeterminista()) is SemFrase.AGUARDANDO_RESERVA


# --- distinguir "vazio" de "espere" ------------------------------------------


def test_colecao_vazia_e_ausencia_de_conteudo() -> None:
    assert selecionar(Ciclo.primeiro(), (), SorteioDeterminista()) is SemFrase.COLECAO_VAZIA


def test_reserva_pendente_e_condicao_temporaria_nao_ausencia() -> None:
    """A diferença decide se o pedido morre ou espera.

    Tudo consumido com uma reserva pendente é transitório: o pedido que segura a
    reserva vai terminar. Tratar isso como "sem conteúdo" encerraria a diária em
    estado terminal, e nem o reconciliador nem a janela até 12:00 a reabririam.
    """
    ciclo = Ciclo.primeiro()
    for frase in ("a", "b"):
        ciclo = ciclo.reservar(frase).consumir(frase)
    ciclo = ciclo.reservar("c")

    assert selecionar(ciclo, TODAS, SorteioDeterminista()) is SemFrase.AGUARDANDO_RESERVA
