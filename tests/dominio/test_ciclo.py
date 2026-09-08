"""Ciclo: o conjunto de frases consumidas desde o último reinício da seleção.

O ciclo é o que faz `/frase` percorrer a coleção inteira sem repetir. Ele guarda
três coisas: o que já foi consumido, o que está reservado por um pedido em
andamento, e qual foi a última frase entregue — esta última só para evitar que o
ciclo seguinte comece repetindo.
"""

import pytest

from frase_diaria.dominio.ciclo import Ciclo

TODAS = ("a", "b", "c")


def test_ciclo_novo_tem_todas_as_frases_elegiveis() -> None:
    assert Ciclo.primeiro().elegiveis(TODAS) == TODAS


def test_consumida_sai_das_elegiveis() -> None:
    ciclo = Ciclo.primeiro().reservar("b").consumir("b")

    assert ciclo.elegiveis(TODAS) == ("a", "c")


def test_reservada_sai_das_elegiveis_sem_estar_consumida() -> None:
    # Uma frase reservada por um pedido em andamento não pode ser sorteada por
    # outro; ela ainda não foi consumida, mas também não está livre.
    ciclo = Ciclo.primeiro().reservar("b")

    assert ciclo.elegiveis(TODAS) == ("a", "c")
    assert not ciclo.foi_consumida("b")


def test_liberar_devolve_a_frase_as_elegiveis() -> None:
    # Falha comprovada sem nenhum envio libera a reserva (spec, 4.4).
    ciclo = Ciclo.primeiro().reservar("b").liberar("b")

    assert ciclo.elegiveis(TODAS) == TODAS
    assert not ciclo.foi_consumida("b")


def test_frase_nova_na_colecao_entra_no_ciclo_atual() -> None:
    # Inserção entra imediatamente, sem esperar o próximo ciclo (AC07).
    ciclo = Ciclo.primeiro().reservar("a").consumir("a")

    assert ciclo.elegiveis(("a", "b", "c", "nova")) == ("b", "c", "nova")


def test_frase_excluida_da_colecao_some_das_elegiveis() -> None:
    # A exclusão remove elegibilidade; o histórico de consumo é preservado.
    ciclo = Ciclo.primeiro().reservar("a").consumir("a")

    assert ciclo.elegiveis(("b", "c")) == ("b", "c")
    assert ciclo.foi_consumida("a")


# --- fim de ciclo ------------------------------------------------------------


def test_ciclo_se_esgota_quando_tudo_foi_consumido() -> None:
    ciclo = Ciclo.primeiro()
    for frase in TODAS:
        ciclo = ciclo.reservar(frase).consumir(frase)

    assert ciclo.esgotado(TODAS)


def test_ciclo_com_reserva_pendente_nao_esta_esgotado() -> None:
    # Um novo ciclo só abre quando não há reservas pendentes: reiniciar com um
    # pedido em andamento poria a mesma frase em dois ciclos.
    ciclo = Ciclo.primeiro().reservar("a").consumir("a").reservar("b").consumir("b").reservar("c")

    assert not ciclo.esgotado(TODAS)


def test_reiniciar_abre_um_ciclo_novo_lembrando_a_ultima_entregue() -> None:
    ciclo = Ciclo.primeiro()
    for frase in TODAS:
        ciclo = ciclo.reservar(frase).consumir(frase)

    novo = ciclo.reiniciar()

    assert novo.numero == ciclo.numero + 1
    assert novo.elegiveis(TODAS) == TODAS
    assert novo.ultima_entregue == "c"


# --- AC05: a virada de ciclo não repete --------------------------------------


def test_com_duas_ou_mais_frases_a_primeira_do_novo_ciclo_evita_a_ultima() -> None:
    ciclo = Ciclo.primeiro()
    for frase in TODAS:
        ciclo = ciclo.reservar(frase).consumir(frase)

    novo = ciclo.reiniciar()

    assert novo.candidatas_a_primeira(TODAS) == ("a", "b")


def test_com_uma_unica_frase_a_repeticao_e_permitida() -> None:
    ciclo = Ciclo.primeiro().reservar("a").consumir("a").reiniciar()

    assert ciclo.candidatas_a_primeira(("a",)) == ("a",)


def test_sem_frases_nao_ha_candidatas() -> None:
    assert Ciclo.primeiro().candidatas_a_primeira(()) == ()


def test_a_exclusao_da_ultima_entregue_nao_impede_o_novo_ciclo() -> None:
    # Se a última entregue foi excluída da coleção, todas as demais servem.
    ciclo = Ciclo.primeiro().reservar("c").consumir("c").reiniciar()

    assert ciclo.candidatas_a_primeira(("a", "b")) == ("a", "b")


def test_candidatas_a_primeira_so_vale_no_comeco_do_ciclo() -> None:
    # Depois da primeira entrega do ciclo, a última do ciclo anterior volta a ser
    # candidata como qualquer outra.
    novo = Ciclo.primeiro().reservar("c").consumir("c").reiniciar()
    depois = novo.reservar("a").consumir("a")

    assert depois.candidatas_a_primeira(TODAS) == ("b", "c")


# --- consumo com ressalva ----------------------------------------------------


def test_consumo_com_ressalva_marca_a_frase_como_usada() -> None:
    # Entrega parcial ou incerta mantém a frase consumida, para não reiniciar
    # automaticamente algo que já pode ter chegado (spec, 4.4).
    ciclo = Ciclo.primeiro().reservar("b").consumir("b", com_ressalva=True)

    assert ciclo.foi_consumida("b")
    assert ciclo.elegiveis(TODAS) == ("a", "c")
    assert ciclo.consumidas_com_ressalva == frozenset({"b"})


def test_consumo_normal_nao_deixa_ressalva() -> None:
    ciclo = Ciclo.primeiro().reservar("b").consumir("b")

    assert ciclo.consumidas_com_ressalva == frozenset()


def test_a_ultima_entregue_muda_a_cada_consumo() -> None:
    ciclo = Ciclo.primeiro().reservar("a").consumir("a").reservar("b").consumir("b")

    assert ciclo.ultima_entregue == "b"


# --- proteções ---------------------------------------------------------------


def test_nao_consome_frase_que_nao_estava_reservada() -> None:
    with pytest.raises(ValueError, match="não está reservada"):
        Ciclo.primeiro().consumir("a")


def test_nao_reserva_frase_ja_consumida_no_ciclo() -> None:
    ciclo = Ciclo.primeiro().reservar("a").consumir("a")

    with pytest.raises(ValueError, match="já consumida"):
        ciclo.reservar("a")


def test_nao_reserva_frase_ja_reservada() -> None:
    ciclo = Ciclo.primeiro().reservar("a")

    with pytest.raises(ValueError, match="já reservada"):
        ciclo.reservar("a")
