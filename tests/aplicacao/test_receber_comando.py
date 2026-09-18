"""Fronteira do webhook: o que acontece quando o Telegram bate na porta.

Duas regras estruturam tudo: o comando é persistido ANTES de a resposta HTTP
confirmar recebimento, e uma conversa não autorizada não recebe resposta nem
gera pedido.
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from frase_diaria.aplicacao.portas import ErroDeEnvio
from frase_diaria.aplicacao.receber_comando import Desfecho, ReceberComando
from frase_diaria.dominio.autorizacao import PoliticaDeAcesso
from frase_diaria.dominio.tempo import politica_do_extra
from frase_diaria.telegram.atualizacao import interpretar

SEGREDO = "segredo-certo"
CHAT = 111111
CHAT_DO_IRMAO = 111222333
POLITICA = PoliticaDeAcesso(segredo_esperado=SEGREDO, chat_ids_autorizados=frozenset({CHAT}))
POLITICA_COM_DOIS_DESTINATARIOS = PoliticaDeAcesso(
    segredo_esperado=SEGREDO, chat_ids_autorizados=frozenset({CHAT, CHAT_DO_IRMAO})
)


class RelogioFixo:
    def agora(self) -> datetime:
        return datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


class RepositorioEmMemoria:
    def __init__(self) -> None:
        self.registrados: list[tuple[int, str]] = []
        self.em_andamento: set[int] = set()
        self.concluidos: set[int] = set()

    def registrar(self, atualizacao, instante) -> bool:  # type: ignore[no-untyped-def]
        chave = (atualizacao.update_id, atualizacao.comando.value)
        if any(u == atualizacao.update_id for u, _ in self.registrados):
            return False
        self.registrados.append(chave)
        return True

    def reivindicar_acao(self, update_id: int) -> bool:
        if update_id in self.em_andamento or update_id in self.concluidos:
            return False
        self.em_andamento.add(update_id)
        return True

    def liberar_acao(self, update_id: int) -> None:
        self.em_andamento.remove(update_id)

    def marcar_acao_concluida(self, update_id: int) -> None:
        self.em_andamento.remove(update_id)
        self.concluidos.add(update_id)


class RepositorioQueFalha:
    def registrar(self, atualizacao, instante) -> bool:  # type: ignore[no-untyped-def]
        raise RuntimeError("DynamoDB indisponível")


class CanalEspiao:
    def __init__(self) -> None:
        self.enviados: list[tuple[int, str]] = []

    def enviar_texto(self, chat_id: int, texto: str) -> int:
        self.enviados.append((chat_id, texto))
        return 900 + len(self.enviados)


def _mensagem(
    texto: str = "/start",
    chat_id: int = CHAT,
    tipo: str = "private",
    update_id: int = 1,
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {"chat": {"id": chat_id, "type": tipo}, "text": texto},
    }


def _caso(repositorio: Any | None = None, canal: Any | None = None) -> ReceberComando:
    return ReceberComando(
        interpretar=interpretar,
        politica=POLITICA,
        repositorio=repositorio if repositorio is not None else RepositorioEmMemoria(),
        canal=canal if canal is not None else CanalEspiao(),
        relogio=RelogioFixo(),
        pedidos=PedidosEspiao(),
        despachante=DespachanteEspiao(),
    )


# --- caminho feliz -----------------------------------------------------------


def test_start_registra_e_responde_a_ajuda() -> None:
    repositorio, canal = RepositorioEmMemoria(), CanalEspiao()

    desfecho = _caso(repositorio, canal).executar(segredo=SEGREDO, corpo=_mensagem("/start"))

    assert desfecho is Desfecho.ACEITO
    assert len(repositorio.registrados) == 1
    assert len(canal.enviados) == 1
    ajuda = canal.enviados[0][1]
    assert "/frase" in ajuda and "/status" in ajuda


def test_comando_desconhecido_autorizado_recebe_ajuda_curta() -> None:
    canal = CanalEspiao()

    desfecho = _caso(canal=canal).executar(segredo=SEGREDO, corpo=_mensagem("bom dia"))

    assert desfecho is Desfecho.ACEITO
    assert "/frase" in canal.enviados[0][1]


# --- AC18: quem não é a usuária não recebe nada ------------------------------


@pytest.mark.parametrize(
    ("descricao", "segredo", "corpo"),
    [
        ("segredo inválido", "errado", _mensagem()),
        ("segredo ausente", None, _mensagem()),
        ("conversa de grupo", SEGREDO, _mensagem(tipo="group")),
        ("outro chat_id", SEGREDO, _mensagem(chat_id=999999)),
    ],
)
def test_entrada_nao_autorizada_nao_responde_e_nao_registra(descricao, segredo, corpo) -> None:  # type: ignore[no-untyped-def]
    repositorio, canal = RepositorioEmMemoria(), CanalEspiao()

    desfecho = _caso(repositorio, canal).executar(segredo=segredo, corpo=corpo)

    assert desfecho is Desfecho.IGNORADO, descricao
    assert repositorio.registrados == [], descricao
    assert canal.enviados == [], descricao


# --- idempotência ------------------------------------------------------------


def test_update_repetido_nao_registra_de_novo_nem_responde_de_novo() -> None:
    repositorio, canal = RepositorioEmMemoria(), CanalEspiao()
    caso = _caso(repositorio, canal)
    corpo = _mensagem("/start", update_id=42)

    primeiro = caso.executar(segredo=SEGREDO, corpo=corpo)
    segundo = caso.executar(segredo=SEGREDO, corpo=corpo)

    assert primeiro is Desfecho.ACEITO
    assert segundo is Desfecho.JA_CONHECIDO
    assert len(repositorio.registrados) == 1
    assert len(canal.enviados) == 1


# --- updates irrelevantes ----------------------------------------------------


def test_update_irrelevante_e_reconhecido_sem_registrar() -> None:
    repositorio, canal = RepositorioEmMemoria(), CanalEspiao()

    irrelevante = {"update_id": 3, "poll": {}}

    desfecho = _caso(repositorio, canal).executar(segredo=SEGREDO, corpo=irrelevante)

    assert desfecho is Desfecho.IGNORADO
    assert repositorio.registrados == []
    assert canal.enviados == []


# --- persistência antes da confirmação ---------------------------------------


def test_falha_ao_persistir_nao_responde_e_pede_reentrega() -> None:
    canal = CanalEspiao()

    caso = _caso(RepositorioQueFalha(), canal)

    desfecho = caso.executar(segredo=SEGREDO, corpo=_mensagem("/start"))

    assert desfecho is Desfecho.NAO_PERSISTIDO
    # Nada foi enviado: responder sem ter registrado deixaria o Telegram
    # reentregar um comando que a usuária já viu respondido.
    assert canal.enviados == []


# --- /frase cria pedido e acorda o worker ------------------------------------


class PedidosEspiao:
    def __init__(self, ja_existe: bool = False) -> None:
        self.criados: list[Any] = []
        self.ja_existe = ja_existe

    def criar_se_ausente(self, pedido: Any, instante: Any) -> bool:
        self.criados.append(pedido)
        return not self.ja_existe


class DespachanteEspiao:
    def __init__(self, falhar: bool = False) -> None:
        self.acordados: list[str] = []
        self.pedidos_de_status: list[int] = []
        self.falhar = falhar

    def acordar(self, identidade: str) -> None:
        if self.falhar:
            raise RuntimeError("Lambda indisponível")
        self.acordados.append(identidade)

    def pedir_status(self, chat_id: int) -> None:
        if self.falhar:
            raise RuntimeError("Lambda indisponível")
        self.pedidos_de_status.append(chat_id)


def _caso_com_pedidos(pedidos: Any, despachante: Any, canal: Any = None) -> ReceberComando:
    return ReceberComando(
        interpretar=interpretar,
        politica=POLITICA,
        repositorio=RepositorioEmMemoria(),
        canal=canal if canal is not None else CanalEspiao(),
        relogio=RelogioFixo(),
        pedidos=pedidos,
        despachante=despachante,
    )


def test_frase_cria_pedido_extra_e_acorda_o_worker() -> None:
    pedidos, despachante = PedidosEspiao(), DespachanteEspiao()

    desfecho = _caso_com_pedidos(pedidos, despachante).executar(
        segredo=SEGREDO, corpo=_mensagem("/frase", update_id=77)
    )

    assert desfecho is Desfecho.ACEITO
    assert pedidos.criados[0].identidade == "extra#principal#77"
    assert pedidos.criados[0].destinatarios == (CHAT,)
    assert despachante.acordados == ["extra#principal#77"]


def test_frase_extra_nasce_com_a_politica_de_retentativa_do_instante_de_criacao() -> None:
    pedidos, despachante = PedidosEspiao(), DespachanteEspiao()

    _caso_com_pedidos(pedidos, despachante).executar(
        segredo=SEGREDO, corpo=_mensagem("/frase", update_id=77)
    )

    politica = politica_do_extra(RelogioFixo().agora())
    assert pedidos.criados[0].prazo == politica.prazo
    assert pedidos.criados[0].tentativa_unica == politica.tentativa_unica


def test_frase_nao_responde_no_webhook() -> None:
    # A frase chega pelo worker; responder aqui duplicaria a mensagem.
    canal = CanalEspiao()

    _caso_com_pedidos(PedidosEspiao(), DespachanteEspiao(), canal).executar(
        segredo=SEGREDO, corpo=_mensagem("/frase", update_id=77)
    )

    assert canal.enviados == []


def test_frase_ja_conhecida_acorda_o_worker_de_novo() -> None:
    """Acordar é idempotente, e pular o despacho perderia o pedido.

    Se a primeira entrega criou o pedido e morreu antes de acordar o worker, a
    reentrega é a única chance de despachá-lo — e ela chega justamente com o
    pedido "já existente".
    """
    pedidos, despachante = PedidosEspiao(ja_existe=True), DespachanteEspiao()

    _caso_com_pedidos(pedidos, despachante).executar(
        segredo=SEGREDO, corpo=_mensagem("/frase", update_id=77)
    )

    assert despachante.acordados == ["extra#principal#77"]


def test_falha_ao_acordar_o_worker_nao_derruba_o_webhook() -> None:
    # O pedido está persistido; o reconciliador o encontrará. Devolver erro faria
    # o Telegram reentregar um comando que já foi registrado.
    pedidos = PedidosEspiao()

    desfecho = _caso_com_pedidos(pedidos, DespachanteEspiao(falhar=True)).executar(
        segredo=SEGREDO, corpo=_mensagem("/frase", update_id=77)
    )

    assert desfecho is Desfecho.ACEITO
    assert pedidos.criados != []


class PedidosQueFalham:
    def criar_se_ausente(self, pedido: Any, instante: Any) -> bool:
        raise RuntimeError("DynamoDB indisponível")


def test_falha_ao_criar_o_pedido_pede_reentrega() -> None:
    """Sem isto, um `/frase` se perde para sempre.

    A exceção subiria pelo FastAPI como 500, o Telegram reentregaria, o registro
    do comando já existiria — devolvendo JA_CONHECIDO e 200 — e o pedido nunca
    seria criado. Comando registrado, frase nunca entregue, sem nova chance.
    """
    desfecho = _caso_com_pedidos(PedidosQueFalham(), DespachanteEspiao()).executar(
        segredo=SEGREDO, corpo=_mensagem("/frase", update_id=77)
    )

    assert desfecho is Desfecho.NAO_PERSISTIDO


def test_reentrega_de_frase_ja_registrada_ainda_garante_o_pedido() -> None:
    """A criação do pedido é idempotente, então repetir é barato e seguro.

    Se a primeira entrega registrou o comando mas morreu antes de criar o pedido,
    é a reentrega que conserta — e ela só conserta se este caminho tentar de novo.
    """
    repositorio = RepositorioEmMemoria()
    pedidos, despachante = PedidosEspiao(), DespachanteEspiao()
    caso = ReceberComando(
        interpretar=interpretar,
        politica=POLITICA,
        repositorio=repositorio,
        canal=CanalEspiao(),
        relogio=RelogioFixo(),
        pedidos=pedidos,
        despachante=despachante,
    )
    corpo = _mensagem("/frase", update_id=77)

    caso.executar(segredo=SEGREDO, corpo=corpo)
    segundo = caso.executar(segredo=SEGREDO, corpo=corpo)

    assert segundo is Desfecho.JA_CONHECIDO
    assert len(pedidos.criados) == 2


class CanalQueFalha:
    def enviar_texto(self, chat_id: int, texto: str) -> int:
        raise RuntimeError("Telegram fora do ar")


class CanalQueRecupera(CanalEspiao):
    def __init__(self) -> None:
        super().__init__()
        self.tentativas = 0

    def enviar_texto(self, chat_id: int, texto: str) -> int:
        self.tentativas += 1
        if self.tentativas == 1:
            raise ErroDeEnvio("Telegram recusou")
        return super().enviar_texto(chat_id, texto)


def test_falha_ambigua_ao_enviar_ajuda_nao_autoriza_reenvio_cego() -> None:
    repositorio = RepositorioEmMemoria()
    caso = _caso(repositorio=repositorio, canal=CanalQueFalha())
    corpo = _mensagem("/start")

    assert caso.executar(segredo=SEGREDO, corpo=corpo) is Desfecho.ACEITO
    assert caso.executar(segredo=SEGREDO, corpo=corpo) is Desfecho.JA_CONHECIDO


def test_reentrega_de_start_repete_somente_a_acao_incompleta() -> None:
    repositorio = RepositorioEmMemoria()
    canal = CanalQueRecupera()
    caso = _caso(repositorio, canal)
    corpo = _mensagem("/start", update_id=77)

    primeiro = caso.executar(segredo=SEGREDO, corpo=corpo)
    segundo = caso.executar(segredo=SEGREDO, corpo=corpo)
    terceiro = caso.executar(segredo=SEGREDO, corpo=corpo)

    assert primeiro is Desfecho.NAO_PERSISTIDO
    assert segundo is Desfecho.JA_CONHECIDO
    assert terceiro is Desfecho.JA_CONHECIDO
    assert len(repositorio.registrados) == 1
    assert len(canal.enviados) == 1


def test_update_irrelevante_sem_segredo_nao_e_reconhecido() -> None:
    """A spec fala em "atualizações irrelevantes **já validadas**" (4.7).

    Decidir que algo é irrelevante antes de conferir o segredo daria a qualquer
    origem uma resposta 200 e uma linha de log.
    """
    repositorio, canal = RepositorioEmMemoria(), CanalEspiao()

    desfecho = _caso(repositorio, canal).executar(
        segredo="errado", corpo={"update_id": 3, "poll": {}}
    )

    assert desfecho is Desfecho.IGNORADO
    assert repositorio.registrados == []


def test_status_nao_responde_no_webhook() -> None:
    # Montar a resposta exige ler o DynamoDB e sincronizar com o Notion — isso
    # é trabalho do worker, não da fronteira HTTP (ticket 15).
    canal = CanalEspiao()

    _caso(canal=canal).executar(segredo=SEGREDO, corpo=_mensagem("/status"))

    assert canal.enviados == []


def test_status_pede_ao_worker_o_relatorio_da_conversa() -> None:
    despachante = DespachanteEspiao()

    desfecho = ReceberComando(
        interpretar=interpretar,
        politica=POLITICA,
        repositorio=RepositorioEmMemoria(),
        canal=CanalEspiao(),
        relogio=RelogioFixo(),
        pedidos=PedidosEspiao(),
        despachante=despachante,
    ).executar(segredo=SEGREDO, corpo=_mensagem("/status"))

    assert desfecho is Desfecho.ACEITO
    assert despachante.pedidos_de_status == [CHAT]


def test_status_repetido_nao_pede_o_relatorio_de_novo() -> None:
    # Idempotência: reentrega do mesmo update_id não deve duplicar o despacho.
    repositorio = RepositorioEmMemoria()
    despachante = DespachanteEspiao()
    caso = ReceberComando(
        interpretar=interpretar,
        politica=POLITICA,
        repositorio=repositorio,
        canal=CanalEspiao(),
        relogio=RelogioFixo(),
        pedidos=PedidosEspiao(),
        despachante=despachante,
    )

    caso.executar(segredo=SEGREDO, corpo=_mensagem("/status", update_id=9))
    desfecho = caso.executar(segredo=SEGREDO, corpo=_mensagem("/status", update_id=9))

    assert desfecho is Desfecho.JA_CONHECIDO
    assert despachante.pedidos_de_status == [CHAT]


# --- múltiplos destinatários (ticket 24) -------------------------------------


@pytest.mark.parametrize("chat_id", [CHAT, CHAT_DO_IRMAO])
def test_frase_funciona_para_qualquer_destinatario_autorizado(chat_id: int) -> None:
    """AC36: um segundo destinatário autorizado usa /frase como qualquer outro."""
    pedidos, despachante = PedidosEspiao(), DespachanteEspiao()
    caso = ReceberComando(
        interpretar=interpretar,
        politica=POLITICA_COM_DOIS_DESTINATARIOS,
        repositorio=RepositorioEmMemoria(),
        canal=CanalEspiao(),
        relogio=RelogioFixo(),
        pedidos=pedidos,
        despachante=despachante,
    )

    desfecho = caso.executar(
        segredo=SEGREDO, corpo=_mensagem("/frase", chat_id=chat_id, update_id=chat_id)
    )

    assert desfecho is Desfecho.ACEITO
    assert pedidos.criados[0].destinatarios == (chat_id,)
    assert despachante.acordados == [f"extra#principal#{chat_id}"]


@pytest.mark.parametrize("chat_id", [CHAT, CHAT_DO_IRMAO])
def test_status_funciona_para_qualquer_destinatario_autorizado(chat_id: int) -> None:
    """AC36: um segundo destinatário autorizado usa /status como qualquer outro."""
    despachante = DespachanteEspiao()
    caso = ReceberComando(
        interpretar=interpretar,
        politica=POLITICA_COM_DOIS_DESTINATARIOS,
        repositorio=RepositorioEmMemoria(),
        canal=CanalEspiao(),
        relogio=RelogioFixo(),
        pedidos=PedidosEspiao(),
        despachante=despachante,
    )

    desfecho = caso.executar(
        segredo=SEGREDO, corpo=_mensagem("/status", chat_id=chat_id, update_id=chat_id)
    )

    assert desfecho is Desfecho.ACEITO
    assert despachante.pedidos_de_status == [chat_id]


def test_recusa_terceiro_chat_id_mesmo_com_dois_destinatarios_autorizados() -> None:
    """AC37: ter mais de um destinatário autorizado não afrouxa a recusa dos demais."""
    repositorio, canal = RepositorioEmMemoria(), CanalEspiao()
    caso = ReceberComando(
        interpretar=interpretar,
        politica=POLITICA_COM_DOIS_DESTINATARIOS,
        repositorio=repositorio,
        canal=canal,
        relogio=RelogioFixo(),
        pedidos=PedidosEspiao(),
        despachante=DespachanteEspiao(),
    )

    desfecho = caso.executar(segredo=SEGREDO, corpo=_mensagem(chat_id=999999))

    assert desfecho is Desfecho.IGNORADO
    assert repositorio.registrados == []
    assert canal.enviados == []


def test_falha_ambigua_ao_pedir_status_nao_redespacha() -> None:
    repositorio = RepositorioEmMemoria()
    despachante = DespachanteEspiao(falhar=True)
    caso = ReceberComando(
        interpretar=interpretar,
        politica=POLITICA,
        repositorio=repositorio,
        canal=CanalEspiao(),
        relogio=RelogioFixo(),
        pedidos=PedidosEspiao(),
        despachante=despachante,
    )
    corpo = _mensagem("/status")

    assert caso.executar(segredo=SEGREDO, corpo=corpo) is Desfecho.ACEITO
    despachante.falhar = False
    assert caso.executar(segredo=SEGREDO, corpo=corpo) is Desfecho.JA_CONHECIDO
    assert despachante.pedidos_de_status == []


def test_claim_de_status_impede_duplo_despacho() -> None:
    repositorio = RepositorioEmMemoria()
    despachante = DespachanteEspiao(falhar=True)
    caso = ReceberComando(
        interpretar=interpretar,
        politica=POLITICA,
        repositorio=repositorio,
        canal=CanalEspiao(),
        relogio=RelogioFixo(),
        pedidos=PedidosEspiao(),
        despachante=despachante,
    )
    corpo = _mensagem("/status", update_id=88)

    assert caso.executar(segredo=SEGREDO, corpo=corpo) is Desfecho.ACEITO
    despachante.falhar = False
    assert caso.executar(segredo=SEGREDO, corpo=corpo) is Desfecho.JA_CONHECIDO
    assert caso.executar(segredo=SEGREDO, corpo=corpo) is Desfecho.JA_CONHECIDO
    assert despachante.pedidos_de_status == []
