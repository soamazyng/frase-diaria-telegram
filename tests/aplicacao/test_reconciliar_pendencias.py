"""O reconciliador: alcança o que o disparo principal não alcançou.

Cobre pedidos pendentes de qualquer origem — não só a diária — porque um
`/frase` que caiu em AGUARDANDO_TENTATIVA por contenção de ciclo também precisa
de alguém que o retome (achado do ticket 06). Dentro da janela até o meio-dia
local, também materializa a diária ausente, cobrindo a falha do disparo
principal do agendador.
"""

from datetime import UTC, datetime

from frase_diaria.aplicacao.reconciliar_pendencias import ReconciliarPendencias
from frase_diaria.dominio.pedido import Origem, Pedido


class RelogioFixo:
    def __init__(self, agora: datetime) -> None:
        self._agora = agora

    def agora(self) -> datetime:
        return self._agora


class PendenciasFalso:
    def __init__(self, vencidos: list[Pedido]) -> None:
        self._vencidos = vencidos
        self.consultas: list[datetime] = []

    def buscar_vencidos(self, instante: datetime) -> list[Pedido]:
        self.consultas.append(instante)
        return self._vencidos


class DespachanteEspiao:
    def __init__(self, falhar_para: set[str] | None = None) -> None:
        self.acordados: list[str] = []
        self._falhar_para = falhar_para or set()

    def acordar(self, identidade: str) -> None:
        if identidade in self._falhar_para:
            raise RuntimeError("Lambda indisponível")
        self.acordados.append(identidade)


class DiariaEspiao:
    def __init__(self, falhar: bool = False) -> None:
        self.chamadas: list[datetime] = []
        self._falhar = falhar

    def executar(self, instante_do_evento: datetime) -> str:
        self.chamadas.append(instante_do_evento)
        if self._falhar:
            raise RuntimeError("DynamoDB indisponível")
        return "diaria#111111#2026-09-07"


def _pedido(identidade: str) -> Pedido:
    return Pedido(identidade=identidade, origem=Origem.EXTRA, destinatarios=(111111,))


def _reconciliador(
    vencidos: list[Pedido], agora: datetime, despachante: DespachanteEspiao | None = None
) -> tuple[ReconciliarPendencias, PendenciasFalso, DespachanteEspiao, DiariaEspiao]:
    pendencias = PendenciasFalso(vencidos)
    despachante = despachante if despachante is not None else DespachanteEspiao()
    diaria = DiariaEspiao()
    reconciliador = ReconciliarPendencias(
        pedidos=pendencias,
        despachante=despachante,
        diaria=diaria,
        relogio=RelogioFixo(agora),
    )
    return reconciliador, pendencias, despachante, diaria


DENTRO_DA_JANELA = datetime(2026, 9, 7, 14, 0, tzinfo=UTC)  # 11:00 em São Paulo
ANTES_DA_JANELA = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)  # 07:00 em São Paulo
DEPOIS_DA_JANELA = datetime(2026, 9, 7, 20, 0, tzinfo=UTC)  # 17:00 em São Paulo


def test_acorda_todos_os_pedidos_vencidos() -> None:
    vencidos = [_pedido("extra#1"), _pedido("diaria#111111#2026-09-07")]
    reconciliador, _, despachante, _ = _reconciliador(vencidos, DEPOIS_DA_JANELA)

    quantidade = reconciliador.executar()

    assert quantidade == 2
    assert despachante.acordados == ["extra#1", "diaria#111111#2026-09-07"]


def test_uma_falha_ao_acordar_nao_impede_os_demais() -> None:
    vencidos = [_pedido("extra#1"), _pedido("extra#2"), _pedido("extra#3")]
    despachante = DespachanteEspiao(falhar_para={"extra#2"})
    reconciliador, _, despachante, _ = _reconciliador(vencidos, DEPOIS_DA_JANELA, despachante)

    quantidade = reconciliador.executar()

    assert quantidade == 2
    assert despachante.acordados == ["extra#1", "extra#3"]


def test_materializa_a_diaria_ausente_dentro_da_janela() -> None:
    reconciliador, _, _, diaria = _reconciliador([], DENTRO_DA_JANELA)

    reconciliador.executar()

    assert diaria.chamadas == [DENTRO_DA_JANELA]


def test_nao_tenta_materializar_a_diaria_antes_das_08_00_locais() -> None:
    reconciliador, _, _, diaria = _reconciliador([], ANTES_DA_JANELA)

    reconciliador.executar()

    assert diaria.chamadas == []


def test_nao_tenta_materializar_a_diaria_depois_do_meio_dia_local() -> None:
    reconciliador, _, _, diaria = _reconciliador([], DEPOIS_DA_JANELA)

    reconciliador.executar()

    assert diaria.chamadas == []


def test_falha_ao_materializar_a_diaria_nao_impede_a_varredura_dos_vencidos() -> None:
    pendencias = PendenciasFalso([_pedido("extra#1")])
    despachante = DespachanteEspiao()
    diaria = DiariaEspiao(falhar=True)
    reconciliador = ReconciliarPendencias(
        pedidos=pendencias,
        despachante=despachante,
        diaria=diaria,
        relogio=RelogioFixo(DENTRO_DA_JANELA),
    )

    quantidade = reconciliador.executar()

    assert quantidade == 1
    assert despachante.acordados == ["extra#1"]
