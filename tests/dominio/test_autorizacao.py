"""AC18: conversa de grupo, chat_id diferente e segredo inválido não produzem
frases nem pedidos autorizados.

A ordem da validação importa: o segredo é conferido primeiro, antes de qualquer
leitura do corpo, para que um chamador sem o segredo não consiga nem descobrir
qual chat_id é o autorizado.
"""

import pytest

from frase_diaria.dominio.autorizacao import (
    Conversa,
    PoliticaDeAcesso,
    Recusa,
)

POLITICA = PoliticaDeAcesso(segredo_esperado="segredo-certo", chat_id_autorizado=8340090374)
CONVERSA_DA_USUARIA = Conversa(chat_id=8340090374, tipo="private")


def test_aceita_a_conversa_privada_autorizada_com_o_segredo_certo() -> None:
    assert POLITICA.avaliar(segredo="segredo-certo", conversa=CONVERSA_DA_USUARIA) is None


def test_recusa_segredo_invalido() -> None:
    recusa = POLITICA.avaliar(segredo="segredo-errado", conversa=CONVERSA_DA_USUARIA)

    assert recusa is Recusa.SEGREDO_INVALIDO


def test_recusa_segredo_ausente() -> None:
    assert POLITICA.avaliar(segredo=None, conversa=CONVERSA_DA_USUARIA) is Recusa.SEGREDO_INVALIDO


def test_recusa_conversa_de_grupo_mesmo_com_segredo_certo() -> None:
    grupo = Conversa(chat_id=8340090374, tipo="group")

    assert POLITICA.avaliar(segredo="segredo-certo", conversa=grupo) is Recusa.CONVERSA_NAO_PRIVADA


@pytest.mark.parametrize("tipo", ["group", "supergroup", "channel"])
def test_recusa_qualquer_tipo_que_nao_seja_privado(tipo: str) -> None:
    conversa = Conversa(chat_id=8340090374, tipo=tipo)

    recusa = POLITICA.avaliar(segredo="segredo-certo", conversa=conversa)

    assert recusa is Recusa.CONVERSA_NAO_PRIVADA


def test_recusa_outro_chat_id_ainda_que_privado() -> None:
    intrusa = Conversa(chat_id=999999, tipo="private")

    assert POLITICA.avaliar(segredo="segredo-certo", conversa=intrusa) is Recusa.CHAT_NAO_AUTORIZADO


def test_o_segredo_e_conferido_antes_do_chat_id() -> None:
    # Um chamador sem o segredo não deve conseguir distinguir "chat errado" de
    # "segredo errado" — senão a resposta vira um oráculo do chat_id autorizado.
    intrusa = Conversa(chat_id=999999, tipo="group")

    assert POLITICA.avaliar(segredo="errado", conversa=intrusa) is Recusa.SEGREDO_INVALIDO


def test_comparacao_do_segredo_nao_vaza_tamanho_por_curto_circuito() -> None:
    # Segredos de tamanhos diferentes devem ser recusados sem exceção.
    assert POLITICA.avaliar(segredo="x", conversa=CONVERSA_DA_USUARIA) is Recusa.SEGREDO_INVALIDO
    longo = POLITICA.avaliar(segredo="s" * 500, conversa=CONVERSA_DA_USUARIA)
    assert longo is Recusa.SEGREDO_INVALIDO
