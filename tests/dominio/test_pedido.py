"""Um pedido de envio tem identidade persistente e estado explícito.

O conjunto completo de estados e as regras de transição são do ticket 07; aqui
está o mínimo que o tracer bullet exige, com o vocabulário definitivo para que o
07 estenda em vez de renomear.
"""

from datetime import date

import pytest

from frase_diaria.dominio.pedido import EstadoDoPedido, Origem, Pedido


def _pedido() -> Pedido:
    return Pedido(identidade="extra#bot-ficticio#42", origem=Origem.EXTRA, chat_id=123456789)


def test_nasce_pendente_e_sem_frase_reservada() -> None:
    pedido = _pedido()

    assert pedido.estado is EstadoDoPedido.PENDENTE
    assert pedido.frase_reservada is None
    assert pedido.motivo_do_estado == "pedido criado"


def test_vocabulario_de_estados_e_completo() -> None:
    assert {estado.value for estado in EstadoDoPedido} == {
        "pendente",
        "reservado",
        "enviando",
        "aguardando_tentativa",
        "enviado",
        "parcial",
        "incerto",
        "falhou",
        "expirado",
    }


def test_identidade_de_um_extra_vem_do_update_id() -> None:
    assert Pedido.identidade_de_extra(bot="bot-ficticio", update_id=42) == "extra#bot-ficticio#42"


def test_identidade_diaria_combina_conversa_e_dia_local() -> None:
    assert (
        Pedido.identidade_de_diaria(chat_id=123456789, dia=date(2026, 9, 7))
        == "diaria#123456789#2026-09-07"
    )


def test_identidades_de_parte_e_tentativa_pertencem_ao_pedido() -> None:
    assert Pedido.identidade_de_parte("extra#bot-ficticio#42", indice=3) == (
        "extra#bot-ficticio#42#parte#3"
    )
    assert Pedido.identidade_de_tentativa("extra#bot-ficticio#42", sequencial=2) == (
        "extra#bot-ficticio#42#tentativa#2"
    )


def test_reservar_e_iniciar_envio_sao_transicoes_distintas_com_motivo() -> None:
    pedido = _pedido().reservar("bloco-7")

    assert pedido.frase_reservada == "bloco-7"
    assert pedido.estado is EstadoDoPedido.RESERVADO
    assert pedido.motivo_do_estado == "frase reservada"

    enviando = pedido.iniciar_envio()

    assert enviando.estado is EstadoDoPedido.ENVIANDO
    assert enviando.motivo_do_estado == "envio iniciado"


def test_confirmar_todas_as_partes_conclui_o_pedido() -> None:
    pedido = _pedido().reservar("bloco-7").iniciar_envio().concluir()

    assert pedido.estado is EstadoDoPedido.ENVIADO
    assert pedido.motivo_do_estado == "todas as partes confirmadas"


def test_falhar_sem_ter_enviado_nada_libera_a_reserva() -> None:
    # Falha comprovada sem envio libera a frase para outro pedido (spec, 4.4).
    pedido = (
        _pedido()
        .reservar("bloco-7")
        .iniciar_envio()
        .falhar(alguma_parte_enviada=False, motivo="Telegram recusou")
    )

    assert pedido.estado is EstadoDoPedido.FALHOU
    assert pedido.frase_reservada is None
    assert pedido.motivo_do_estado == "Telegram recusou"


def test_falhar_depois_de_enviar_parte_mantem_a_frase_consumida() -> None:
    # Entrega parcial mantém a frase usada, para não reiniciar algo que já chegou.
    pedido = (
        _pedido()
        .reservar("bloco-7")
        .iniciar_envio()
        .falhar(alguma_parte_enviada=True, motivo="segunda parte falhou")
    )

    assert pedido.estado is EstadoDoPedido.PARCIAL
    assert pedido.frase_reservada == "bloco-7"


def test_estado_terminal_nao_reabre() -> None:
    concluido = _pedido().reservar("bloco-7").iniciar_envio().concluir()

    with pytest.raises(ValueError, match="terminal"):
        concluido.reservar("bloco-8")


def test_nao_conclui_um_pedido_sem_frase_reservada() -> None:
    with pytest.raises(ValueError, match="sem frase reservada"):
        _pedido().concluir()


def test_aguardar_tentativa_e_retomar_o_envio() -> None:
    aguardando = _pedido().aguardar_tentativa("todas as frases estão reservadas")

    assert aguardando.estado is EstadoDoPedido.AGUARDANDO_TENTATIVA
    assert aguardando.motivo_do_estado == "todas as frases estão reservadas"

    retomado = aguardando.reservar("bloco-7").iniciar_envio()

    assert retomado.estado is EstadoDoPedido.ENVIANDO


def test_entrega_ambigua_fica_incerta_e_terminal() -> None:
    incerto = (
        _pedido()
        .reservar("bloco-7")
        .iniciar_envio()
        .marcar_incerto("Telegram pode ter aceitado a parte")
    )

    assert incerto.estado is EstadoDoPedido.INCERTO
    assert incerto.motivo_do_estado == "Telegram pode ter aceitado a parte"
    assert incerto.estado.terminal


def test_pedido_pode_expirar_com_motivo() -> None:
    expirado = _pedido().expirar("janela de recuperação encerrada")

    assert expirado.estado is EstadoDoPedido.EXPIRADO
    assert expirado.motivo_do_estado == "janela de recuperação encerrada"
    assert expirado.estado.terminal


def test_transicao_invalida_e_rejeitada() -> None:
    with pytest.raises(ValueError, match="transição inválida"):
        _pedido().iniciar_envio()


def test_motivo_vazio_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="motivo"):
        _pedido().aguardar_tentativa("")
