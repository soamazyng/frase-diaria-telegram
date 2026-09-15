"""Materializa o pedido diário a partir do disparo do agendador.

A identidade (dia local — v2) já torna a chamada idempotente — o agendador e o
reconciliador podem chamar de novo sem duplicar a diária. A partir da v2, um
único pedido carrega todos os destinatários autorizados: não há mais um pedido
por chat_id.
"""

from datetime import UTC, datetime

from frase_diaria.aplicacao.criar_diaria import CriarDiaria
from frase_diaria.dominio.pedido import Origem, Pedido
from frase_diaria.dominio.tempo import prazo_da_diaria


class CriadorDePedidosFalso:
    def __init__(self) -> None:
        self.criados: list[tuple[Pedido, datetime]] = []

    def criar_se_ausente(self, pedido: Pedido, instante: datetime) -> bool:
        self.criados.append((pedido, instante))
        return True


CHAT = 672024065
CHAT_DO_IRMAO = 111222333


def test_materializa_o_pedido_diario_para_todos_os_destinatarios() -> None:
    pedidos = CriadorDePedidosFalso()
    instante = datetime(2026, 9, 7, 11, 0, tzinfo=UTC)  # 08:00 em São Paulo

    identidade = CriarDiaria(pedidos=pedidos, destinatarios=(CHAT, CHAT_DO_IRMAO)).executar(
        instante
    )

    assert identidade == "diaria#2026-09-07"
    assert len(pedidos.criados) == 1
    pedido, criado_em = pedidos.criados[0]
    assert pedido.identidade == identidade
    assert pedido.origem is Origem.DIARIA
    assert pedido.destinatarios == (CHAT, CHAT_DO_IRMAO)
    assert criado_em == instante


def test_o_pedido_diario_nasce_com_prazo_ate_o_meio_dia_local() -> None:
    pedidos = CriadorDePedidosFalso()
    instante = datetime(2026, 9, 7, 11, 0, tzinfo=UTC)

    CriarDiaria(pedidos=pedidos, destinatarios=(CHAT,)).executar(instante)

    pedido, _ = pedidos.criados[0]
    assert pedido.prazo == prazo_da_diaria(instante.date())


def test_e_idempotente_por_identidade() -> None:
    class CriadorQueRecusaRepeticao(CriadorDePedidosFalso):
        def criar_se_ausente(self, pedido: Pedido, instante: datetime) -> bool:
            super().criar_se_ausente(pedido, instante)
            return len(self.criados) == 1

    pedidos = CriadorQueRecusaRepeticao()
    instante = datetime(2026, 9, 7, 11, 0, tzinfo=UTC)
    diaria = CriarDiaria(pedidos=pedidos, destinatarios=(CHAT,))

    primeira = diaria.executar(instante)
    segunda = diaria.executar(instante)

    assert primeira == segunda
    assert len(pedidos.criados) == 2  # ambas as chamadas tentam; a identidade é igual


def test_identidade_nao_depende_de_quais_destinatarios_estao_configurados() -> None:
    """Duas execuções no mesmo dia produzem a mesma identidade mesmo se o
    conjunto de destinatários mudar entre elas — a diária é uma por dia, não
    uma por combinação de destinatários."""
    pedidos = CriadorDePedidosFalso()
    instante = datetime(2026, 9, 7, 11, 0, tzinfo=UTC)

    com_um = CriarDiaria(pedidos=pedidos, destinatarios=(CHAT,)).executar(instante)
    com_dois = CriarDiaria(pedidos=pedidos, destinatarios=(CHAT, CHAT_DO_IRMAO)).executar(instante)

    assert com_um == com_dois == "diaria#2026-09-07"
