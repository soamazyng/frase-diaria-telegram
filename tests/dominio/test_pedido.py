"""Um pedido de envio tem identidade persistente e estado explícito.

O conjunto completo de estados e as regras de transição são do ticket 07; aqui
está o mínimo que o tracer bullet exige, com o vocabulário definitivo para que o
07 estenda em vez de renomear.
"""

import pytest

from frase_diaria.dominio.pedido import EstadoDoPedido, Origem, Pedido


def _pedido() -> Pedido:
    return Pedido(identidade="extra#42", origem=Origem.EXTRA, chat_id=672024065)


def test_nasce_pendente_e_sem_frase_reservada() -> None:
    pedido = _pedido()

    assert pedido.estado is EstadoDoPedido.PENDENTE
    assert pedido.frase_reservada is None


def test_identidade_de_um_extra_vem_do_update_id() -> None:
    assert Pedido.identidade_de_extra(update_id=42) == "extra#42"


def test_reservar_frase_move_para_enviando() -> None:
    pedido = _pedido().reservar("bloco-7")

    assert pedido.frase_reservada == "bloco-7"
    assert pedido.estado is EstadoDoPedido.ENVIANDO


def test_confirmar_todas_as_partes_conclui_o_pedido() -> None:
    pedido = _pedido().reservar("bloco-7").concluir()

    assert pedido.estado is EstadoDoPedido.ENVIADO


def test_falhar_sem_ter_enviado_nada_libera_a_reserva() -> None:
    # Falha comprovada sem envio libera a frase para outro pedido (spec, 4.4).
    pedido = _pedido().reservar("bloco-7").falhar(alguma_parte_enviada=False)

    assert pedido.estado is EstadoDoPedido.FALHOU
    assert pedido.frase_reservada is None


def test_falhar_depois_de_enviar_parte_mantem_a_frase_consumida() -> None:
    # Entrega parcial mantém a frase usada, para não reiniciar algo que já chegou.
    pedido = _pedido().reservar("bloco-7").falhar(alguma_parte_enviada=True)

    assert pedido.estado is EstadoDoPedido.PARCIAL
    assert pedido.frase_reservada == "bloco-7"


def test_estado_terminal_nao_reabre() -> None:
    concluido = _pedido().reservar("bloco-7").concluir()

    with pytest.raises(ValueError, match="terminal"):
        concluido.reservar("bloco-8")


def test_nao_conclui_um_pedido_sem_frase_reservada() -> None:
    with pytest.raises(ValueError, match="sem frase reservada"):
        _pedido().concluir()
