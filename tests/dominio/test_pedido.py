"""Um pedido de envio tem identidade persistente e estado explícito.

O conjunto completo de estados e as regras de transição são do ticket 07; aqui
está o mínimo que o tracer bullet exige, com o vocabulário definitivo para que o
07 estenda em vez de renomear.
"""

from datetime import UTC, date, datetime

import pytest

from frase_diaria.dominio.pedido import EstadoDoPedido, Origem, Pedido


def _pedido() -> Pedido:
    return Pedido(
        identidade="extra#bot-ficticio#42", origem=Origem.EXTRA, destinatarios=(123456789,)
    )


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


def test_identidade_diaria_combina_com_o_dia_local() -> None:
    """A partir da v2, a diária é um único pedido para todo o conjunto de
    destinatários — a identidade não carrega mais um chat_id específico
    (spec v2, `.scratch/v2-telegram-bot.md`)."""
    assert Pedido.identidade_de_diaria(dia=date(2026, 9, 7)) == "diaria#2026-09-07"


def test_dia_alvo_da_diaria_vem_da_identidade() -> None:
    diaria = Pedido(
        identidade=Pedido.identidade_de_diaria(dia=date(2026, 9, 7)),
        origem=Origem.DIARIA,
        destinatarios=(123456789,),
    )

    assert diaria.dia_alvo_da_diaria() == date(2026, 9, 7)


def test_dia_alvo_da_diaria_e_none_para_um_extra() -> None:
    assert _pedido().dia_alvo_da_diaria() is None


def test_identidades_de_parte_e_tentativa_pertencem_ao_pedido() -> None:
    identidade_de_parte = Pedido.identidade_de_parte(
        "extra#bot-ficticio#42", destinatario=123456789, indice=3
    )
    assert identidade_de_parte == "extra#bot-ficticio#42#dest#123456789#parte#3"
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


def test_aguardar_tentativa_sem_novo_prazo_preserva_o_proximo_instante() -> None:
    # A retentativa por contenção de ciclo (ticket 09) não muda o agendamento.
    original = date(2026, 9, 7)
    pedido = Pedido(
        identidade="diaria#2026-09-07",
        origem=Origem.DIARIA,
        destinatarios=(123,),
        proxima_tentativa=datetime(2026, 9, 7, 11, 0, tzinfo=UTC),
    )
    assert original  # apenas para deixar claro que a data não participa aqui

    aguardando = pedido.aguardar_tentativa("todas as frases estão reservadas")

    assert aguardando.proxima_tentativa == datetime(2026, 9, 7, 11, 0, tzinfo=UTC)


def test_aguardar_tentativa_pode_agendar_um_novo_proximo_instante() -> None:
    # Erro transitório do Telegram: o worker calcula o próximo instante com
    # espera progressiva e o passa explicitamente (ticket 14).
    proximo = datetime(2026, 9, 7, 11, 5, tzinfo=UTC)

    aguardando = _pedido().aguardar_tentativa("Bot API respondeu HTTP 500", proximo)

    assert aguardando.proxima_tentativa == proximo


def test_liberar_frase_excluida_volta_para_antes_da_reserva() -> None:
    # A frase reservada sumiu da fonte antes de qualquer parte enviada: volta a
    # um estado que aceita reservar outra, sem terminar o pedido (spec, 4.2).
    reservado = _pedido().reservar("bloco-7")

    liberado = reservado.liberar_frase_excluida("frase reservada não está mais na coleção")

    assert liberado.estado is EstadoDoPedido.AGUARDANDO_TENTATIVA
    assert liberado.frase_reservada is None
    assert liberado.motivo_do_estado == "frase reservada não está mais na coleção"

    trocado = liberado.reservar("bloco-8")
    assert trocado.frase_reservada == "bloco-8"


def test_liberar_frase_excluida_tambem_funciona_apos_iniciar_envio() -> None:
    # Uma retomada pode encontrar o pedido já em ENVIANDO (sem nenhuma parte
    # confirmada ainda) quando a frase reservada desaparece da fonte.
    enviando = _pedido().reservar("bloco-7").iniciar_envio()

    liberado = enviando.liberar_frase_excluida("frase reservada não está mais na coleção")

    assert liberado.estado is EstadoDoPedido.AGUARDANDO_TENTATIVA
    assert liberado.frase_reservada is None


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


def test_expirar_libera_a_reserva_como_uma_falha_sem_envio() -> None:
    # Mesma regra de falhar(alguma_parte_enviada=False): nada foi entregue,
    # então a frase volta a ficar elegível para outro pedido (spec, 4.4).
    expirado = _pedido().reservar("bloco-7").expirar("janela de recuperação encerrada")

    assert expirado.frase_reservada is None


def test_pedido_nasce_sem_prazo_por_padrao() -> None:
    # Pedidos persistidos antes deste ticket não têm prazo gravado; ausência de
    # prazo nunca deve impedir uma retentativa (compatibilidade retroativa).
    assert _pedido().prazo is None


def test_pedido_nasce_sem_tentativa_unica_por_padrao() -> None:
    assert _pedido().tentativa_unica is False


def test_pedido_pode_nascer_com_um_prazo_explicito() -> None:
    prazo = datetime(2026, 9, 7, 15, 0, tzinfo=UTC)

    pedido = Pedido(
        identidade="diaria#2026-09-07", origem=Origem.DIARIA, destinatarios=(123,), prazo=prazo
    )

    assert pedido.prazo == prazo


def test_transicao_invalida_e_rejeitada() -> None:
    with pytest.raises(ValueError, match="transição inválida"):
        _pedido().iniciar_envio()


def test_motivo_vazio_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="motivo"):
        _pedido().aguardar_tentativa("")


# --- múltiplos destinatários (ticket 25) --------------------------------------


def test_pedido_pode_ter_varios_destinatarios() -> None:
    """A diária compartilhada carrega todos os destinatários autorizados."""
    diaria = Pedido(
        identidade=Pedido.identidade_de_diaria(dia=date(2026, 9, 7)),
        origem=Origem.DIARIA,
        destinatarios=(123456789, 111222333),
    )

    assert diaria.destinatarios == (123456789, 111222333)


def test_pedido_sem_nenhum_destinatario_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="destinatário"):
        Pedido(identidade="extra#bot-ficticio#42", origem=Origem.EXTRA, destinatarios=())
