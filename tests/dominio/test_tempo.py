from datetime import UTC, datetime

import pytest

from frase_diaria.dominio.tempo import FUSO_LOCAL, dia_local


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
