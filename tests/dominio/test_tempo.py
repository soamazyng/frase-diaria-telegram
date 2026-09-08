from datetime import UTC, date, datetime

import pytest

from frase_diaria.dominio.tempo import FUSO_LOCAL, dia_local, politica_do_extra, prazo_da_diaria


def test_fuso_local_e_sao_paulo() -> None:
    assert str(FUSO_LOCAL) == "America/Sao_Paulo"


def test_dia_local_usa_o_calendario_de_sao_paulo_e_nao_o_utc() -> None:
    # 03:00 UTC de 07/09 já é 00:00 de 07/09 em São Paulo (UTC-3).
    instante = datetime(2026, 9, 7, 3, 0, tzinfo=UTC)
    assert dia_local(instante).isoformat() == "2026-09-07"


def test_dia_local_vira_o_dia_antes_da_meia_noite_utc() -> None:
    # 02:00 UTC de 07/09 ainda é 23:00 de 06/09 em São Paulo: a chave diária é 06/09.
    instante = datetime(2026, 9, 7, 2, 0, tzinfo=UTC)
    assert dia_local(instante).isoformat() == "2026-09-06"


def test_dia_local_recusa_instante_sem_fuso() -> None:
    with pytest.raises(ValueError, match="fuso"):
        dia_local(datetime(2026, 9, 7, 3, 0))


def test_prazo_da_diaria_e_meio_dia_local_em_utc() -> None:
    # Meio-dia em São Paulo (UTC-3) é 15:00 UTC.
    prazo = prazo_da_diaria(date(2026, 9, 7))

    assert prazo == datetime(2026, 9, 7, 15, 0, tzinfo=UTC)


def test_extra_criado_de_manha_retenta_ate_o_meio_dia_local() -> None:
    criado_em = datetime(2026, 9, 7, 13, 0, tzinfo=UTC)  # 10:00 em São Paulo

    politica = politica_do_extra(criado_em)

    assert politica.prazo == datetime(2026, 9, 7, 15, 0, tzinfo=UTC)
    assert politica.tentativa_unica is False


def test_extra_criado_a_partir_do_meio_dia_tem_tentativa_unica_sem_prazo() -> None:
    # Política decidida pela usuária: sem fila para o dia seguinte, então um
    # extra criado a partir do meio-dia local não ganha nenhuma retentativa —
    # e não tem prazo datado, porque o despacho é sempre um pouco posterior à
    # criação e qualquer prazo próximo dela seria ultrapassado antes mesmo da
    # tentativa única rodar.
    criado_em = datetime(2026, 9, 7, 16, 0, tzinfo=UTC)  # 13:00 em São Paulo

    politica = politica_do_extra(criado_em)

    assert politica.prazo is None
    assert politica.tentativa_unica is True


def test_extra_criado_exatamente_ao_meio_dia_tem_tentativa_unica() -> None:
    criado_em = datetime(2026, 9, 7, 15, 0, tzinfo=UTC)  # 12:00 em São Paulo

    politica = politica_do_extra(criado_em)

    assert politica.prazo is None
    assert politica.tentativa_unica is True
