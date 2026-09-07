from datetime import UTC, datetime

from frase_diaria.aplicacao.consultar_saude import ConsultarSaude


class RelogioFixo:
    def __init__(self, instante: datetime) -> None:
        self._instante = instante

    def agora(self) -> datetime:
        return self._instante


def test_relata_a_versao_da_aplicacao_e_o_instante_do_relogio() -> None:
    relogio = RelogioFixo(datetime(2026, 9, 6, 11, 0, tzinfo=UTC))

    saude = ConsultarSaude(relogio=relogio, versao="abc1234").executar()

    assert saude.versao == "abc1234"
    assert saude.instante == datetime(2026, 9, 6, 11, 0, tzinfo=UTC)


def test_o_relogio_e_substituivel_nos_testes() -> None:
    primeiro = ConsultarSaude(
        relogio=RelogioFixo(datetime(2026, 1, 1, tzinfo=UTC)), versao="v1"
    ).executar()
    segundo = ConsultarSaude(
        relogio=RelogioFixo(datetime(2027, 1, 1, tzinfo=UTC)), versao="v1"
    ).executar()

    assert primeiro.instante != segundo.instante
