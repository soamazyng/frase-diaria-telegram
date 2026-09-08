"""Materializa o pedido diário a partir do disparo do agendador.

A identidade (conversa autorizada + dia local) já torna a chamada idempotente
— o agendador e o reconciliador podem chamar de novo sem duplicar a diária.
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


def test_materializa_o_pedido_diario_da_conversa_autorizada() -> None:
    pedidos = CriadorDePedidosFalso()
    instante = datetime(2026, 9, 7, 11, 0, tzinfo=UTC)  # 08:00 em São Paulo

    identidade = CriarDiaria(pedidos=pedidos, chat_id=CHAT).executar(instante)

    assert identidade == "diaria#672024065#2026-09-07"
    assert len(pedidos.criados) == 1
    pedido, criado_em = pedidos.criados[0]
    assert pedido.identidade == identidade
    assert pedido.origem is Origem.DIARIA
    assert pedido.chat_id == CHAT
    assert criado_em == instante


def test_o_pedido_diario_nasce_com_prazo_ate_o_meio_dia_local() -> None:
    pedidos = CriadorDePedidosFalso()
    instante = datetime(2026, 9, 7, 11, 0, tzinfo=UTC)

    CriarDiaria(pedidos=pedidos, chat_id=CHAT).executar(instante)

    pedido, _ = pedidos.criados[0]
    assert pedido.prazo == prazo_da_diaria(instante.date())


def test_e_idempotente_por_identidade() -> None:
    class CriadorQueRecusaRepeticao(CriadorDePedidosFalso):
        def criar_se_ausente(self, pedido: Pedido, instante: datetime) -> bool:
            super().criar_se_ausente(pedido, instante)
            return len(self.criados) == 1

    pedidos = CriadorQueRecusaRepeticao()
    instante = datetime(2026, 9, 7, 11, 0, tzinfo=UTC)
    diaria = CriarDiaria(pedidos=pedidos, chat_id=CHAT)

    primeira = diaria.executar(instante)
    segunda = diaria.executar(instante)

    assert primeira == segunda
    assert len(pedidos.criados) == 2  # ambas as chamadas tentam; a identidade é igual
