from datetime import UTC, date, datetime

from frase_diaria.dominio.pedido import EstadoDoPedido
from frase_diaria.dominio.status import (
    RelatorioDeStatus,
    SituacaoDaDiaria,
    SituacaoDaSincronizacao,
    UltimoEnvio,
)
from frase_diaria.telegram.status import formatar_status

# 10:00 em São Paulo (UTC-3).
INSTANTE = datetime(2026, 9, 7, 13, 0, tzinfo=UTC)


def _relatorio(
    situacao: SituacaoDaDiaria | None = None,
    ultimo_envio: UltimoEnvio | None = None,
    sincronizacao: SituacaoDaSincronizacao | None = None,
) -> RelatorioDeStatus:
    return RelatorioDeStatus(
        situacao_da_diaria_de_hoje=situacao
        or SituacaoDaDiaria(existe=False, estado=None, motivo=None, tem_partes_incertas=False),
        ultimo_envio=ultimo_envio,
        proxima_ocorrencia_diaria=datetime(2026, 9, 8, 11, 0, tzinfo=UTC),
        sincronizacao=sincronizacao
        or SituacaoDaSincronizacao(
            colecao_disponivel=True,
            usou_cache=False,
            instante_da_ultima_valida=INSTANTE,
            instante_da_ultima_tentativa=INSTANTE,
            erro=None,
        ),
    )


def test_diaria_ausente_aparece_como_ainda_nao_criada() -> None:
    texto = formatar_status(_relatorio())

    assert "ainda não" in texto.lower()


def test_diaria_pendente_mostra_o_estado() -> None:
    situacao = SituacaoDaDiaria(
        existe=True,
        estado=EstadoDoPedido.PENDENTE,
        motivo="pedido criado",
        tem_partes_incertas=False,
    )

    texto = formatar_status(_relatorio(situacao=situacao))

    assert "pendente" in texto.lower()


def test_diaria_falhou_mostra_o_motivo_sanitizado() -> None:
    situacao = SituacaoDaDiaria(
        existe=True,
        estado=EstadoDoPedido.FALHOU,
        motivo="Bot API respondeu HTTP 401",
        tem_partes_incertas=False,
    )

    texto = formatar_status(_relatorio(situacao=situacao))

    assert "Bot API respondeu HTTP 401" in texto


def test_partes_incertas_da_diaria_de_hoje_aparecem_explicitamente() -> None:
    situacao = SituacaoDaDiaria(
        existe=True,
        estado=EstadoDoPedido.INCERTO,
        motivo="Telegram pode ter aceitado a parte",
        tem_partes_incertas=True,
    )

    texto = formatar_status(_relatorio(situacao=situacao))

    assert "não serão reenviadas automaticamente" in texto.lower()


def test_ultimo_envio_nunca() -> None:
    texto = formatar_status(_relatorio())

    assert "nunca" in texto.lower()


def test_ultimo_envio_mostra_o_dia_e_o_estado() -> None:
    ultimo = UltimoEnvio(
        dia=date(2026, 9, 6), estado=EstadoDoPedido.PARCIAL, tem_partes_incertas=False
    )

    texto = formatar_status(_relatorio(ultimo_envio=ultimo))

    assert "06/09" in texto
    assert "parcial" in texto.lower()


def test_ultimo_envio_com_partes_incertas_tambem_e_sinalizado() -> None:
    ultimo = UltimoEnvio(
        dia=date(2026, 9, 6), estado=EstadoDoPedido.INCERTO, tem_partes_incertas=True
    )

    texto = formatar_status(_relatorio(ultimo_envio=ultimo))

    assert "incerta" in texto.lower()


def test_ultimo_envio_incerto_nao_e_chamado_de_confirmado() -> None:
    # "Confirmado" é vocabulário reservado a sucesso com confirmação
    # persistida (CLAUDE.md); um envio parcial ou incerto não pode reivindicar
    # essa palavra, mesmo aparecendo como "o mais recente que chegou".
    ultimo = UltimoEnvio(
        dia=date(2026, 9, 6), estado=EstadoDoPedido.INCERTO, tem_partes_incertas=True
    )

    texto = formatar_status(_relatorio(ultimo_envio=ultimo))

    assert "confirmado" not in texto.lower()


def test_proxima_ocorrencia_em_horario_local() -> None:
    texto = formatar_status(_relatorio())

    # 08:00 em São Paulo de 08/09 — nunca a hora UTC crua (11:00).
    assert "08/09" in texto
    assert "08:00" in texto
    assert "11:00" not in texto


def test_sincronizacao_via_notion_sem_cache() -> None:
    texto = formatar_status(_relatorio())

    assert "notion" in texto.lower()
    assert "cache" not in texto.lower()


def test_sincronizacao_via_cache_aparece_explicitamente() -> None:
    sincronizacao = SituacaoDaSincronizacao(
        colecao_disponivel=True,
        usou_cache=True,
        instante_da_ultima_valida=INSTANTE,
        instante_da_ultima_tentativa=INSTANTE,
        erro="Notion respondeu HTTP 503",
    )

    texto = formatar_status(_relatorio(sincronizacao=sincronizacao))

    assert "cache" in texto.lower()
    assert "Notion respondeu HTTP 503" in texto


def test_sincronizacao_sem_colecao_disponivel() -> None:
    sincronizacao = SituacaoDaSincronizacao(
        colecao_disponivel=False,
        usou_cache=False,
        instante_da_ultima_valida=None,
        instante_da_ultima_tentativa=INSTANTE,
        erro="Notion respondeu HTTP 500",
    )

    texto = formatar_status(_relatorio(sincronizacao=sincronizacao))

    assert "sem coleção válida" in texto.lower()
    assert "Notion respondeu HTTP 500" in texto


def test_sem_nenhuma_tentativa_de_sincronizacao_mostra_nunca() -> None:
    sincronizacao = SituacaoDaSincronizacao(
        colecao_disponivel=False,
        usou_cache=False,
        instante_da_ultima_valida=None,
        instante_da_ultima_tentativa=None,
        erro=None,
    )

    texto = formatar_status(_relatorio(sincronizacao=sincronizacao))

    assert "última tentativa de sincronização: nunca" in texto.lower()


def test_resposta_nao_contem_caracteres_html_nao_escapados_do_motivo() -> None:
    # parse_mode=HTML é sempre enviado (telegram/canal.py); um "<" ou "&" cru no
    # motivo quebraria a mensagem ou seria interpretado como marcação.
    situacao = SituacaoDaDiaria(
        existe=True,
        estado=EstadoDoPedido.FALHOU,
        motivo="erro <script>&teste",
        tem_partes_incertas=False,
    )

    texto = formatar_status(_relatorio(situacao=situacao))

    assert "<script>" not in texto
    assert "&lt;script&gt;" in texto
