"""`/status` monta um retrato do sistema sem consumir frase, tocar o ciclo ou sincronizar.

Por isso `ConsultarStatus` só recebe um repositório de pedidos e um repositório
de coleção, ambos de leitura — nem ciclo, nem reserva, nem um sincronizador de
verdade existem aqui para chamar. Os dados de sincronização vêm do que a
última tentativa real (diária, extra ou reconciliador) já deixou persistido.
"""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from frase_diaria.aplicacao.consultar_status import ConsultarStatus, EnviarStatus
from frase_diaria.dominio.colecao import ColecaoValida, SnapshotPersistido, TentativaDeSincronizacao
from frase_diaria.dominio.pedido import EstadoDoPedido, Origem, Pedido

CHAT = 101
HOJE = date(2026, 9, 7)
AGORA = datetime(2026, 9, 7, 13, 0, tzinfo=UTC)  # 10:00 em São Paulo
COLECAO_VAZIA = ColecaoValida(itens=())


class RelogioFixo:
    def agora(self) -> datetime:
        return AGORA


class RepositorioFalso:
    def __init__(self, pedidos: dict[str, Pedido] | None = None) -> None:
        self._pedidos = pedidos or {}
        self._incertas: dict[tuple[str, int], set[int]] = {}
        self._confirmadas: dict[tuple[str, int], set[int]] = {}

    def obter(self, identidade: str) -> Pedido | None:
        return self._pedidos.get(identidade)

    def marcar_incerta(self, identidade: str, destinatario: int, indice: int) -> None:
        self._incertas.setdefault((identidade, destinatario), set()).add(indice)

    def marcar_confirmada(self, identidade: str, destinatario: int, indice: int) -> None:
        self._confirmadas.setdefault((identidade, destinatario), set()).add(indice)

    def indices_incertos(self, identidade: str, destinatario: int) -> set[int]:
        return self._incertas.get((identidade, destinatario), set())

    def indices_confirmados(self, identidade: str, destinatario: int) -> set[int]:
        return self._confirmadas.get((identidade, destinatario), set())


class ColecaoFalsa:
    def __init__(
        self,
        ativa: SnapshotPersistido | None = None,
        tentativa: TentativaDeSincronizacao | None = None,
    ) -> None:
        self._ativa = ativa
        self._tentativa = tentativa

    def carregar_ativa(self) -> SnapshotPersistido | None:
        return self._ativa

    def ultima_tentativa(self) -> TentativaDeSincronizacao | None:
        return self._tentativa


def _colecao_valida(usou_cache: bool = False, erro: str | None = None) -> ColecaoFalsa:
    instante_do_snapshot = AGORA - timedelta(hours=1) if usou_cache else AGORA
    return ColecaoFalsa(
        ativa=SnapshotPersistido(
            identificador="snap-1", colecao=COLECAO_VAZIA, instante=instante_do_snapshot
        ),
        tentativa=TentativaDeSincronizacao(instante=AGORA, erro=erro),
    )


def _consultar(repositorio: Any, colecao: Any = None, chat_id: int = CHAT) -> ConsultarStatus:
    return ConsultarStatus(
        repositorio=repositorio,
        colecao=colecao if colecao is not None else _colecao_valida(),
        relogio=RelogioFixo(),
        chat_id=chat_id,
    )


def _diaria(dia: date, estado_final: str | None = None) -> Pedido:
    pedido = Pedido(
        identidade=Pedido.identidade_de_diaria(dia), origem=Origem.DIARIA, destinatarios=(CHAT,)
    )
    if estado_final == "enviado":
        return pedido.reservar("bloco-1").iniciar_envio().concluir()
    if estado_final == "falhou":
        return (
            pedido.reservar("bloco-1")
            .iniciar_envio()
            .falhar(alguma_parte_enviada=False, motivo="Bot API respondeu HTTP 401")
        )
    if estado_final == "parcial":
        return (
            pedido.reservar("bloco-1")
            .iniciar_envio()
            .falhar(alguma_parte_enviada=True, motivo="Bot API respondeu HTTP 500")
        )
    return pedido


# --- situação da diária de hoje ------------------------------------------------


def test_diaria_de_hoje_ausente() -> None:
    relatorio = _consultar(RepositorioFalso()).executar()

    assert relatorio.situacao_da_diaria_de_hoje.existe is False
    assert relatorio.situacao_da_diaria_de_hoje.estado is None


def test_diaria_de_hoje_pendente() -> None:
    identidade = Pedido.identidade_de_diaria(HOJE)
    repositorio = RepositorioFalso({identidade: _diaria(HOJE)})

    relatorio = _consultar(repositorio).executar()

    assert relatorio.situacao_da_diaria_de_hoje.existe is True
    assert relatorio.situacao_da_diaria_de_hoje.estado is EstadoDoPedido.PENDENTE


def test_diaria_de_hoje_com_partes_incertas() -> None:
    identidade = Pedido.identidade_de_diaria(HOJE)
    diaria = (
        _diaria(HOJE)
        .reservar("bloco-1")
        .iniciar_envio()
        .marcar_incerto("Telegram pode ter aceitado")
    )
    repositorio = RepositorioFalso({identidade: diaria})
    repositorio.marcar_incerta(identidade, CHAT, 0)

    relatorio = _consultar(repositorio).executar()

    assert relatorio.situacao_da_diaria_de_hoje.tem_partes_incertas is True


# --- múltiplos destinatários: cada um vê a própria entrega (ticket 26) --------

CHAT_DO_IRMAO = 111222333


def test_dois_destinatarios_com_desfechos_diferentes_veem_status_diferentes() -> None:
    """AC35: quem recebeu tudo não vê 'incerto' só porque o outro destinatário
    ficou incerto na mesma diária compartilhada."""
    identidade = Pedido.identidade_de_diaria(HOJE)
    diaria_compartilhada = Pedido(
        identidade=identidade,
        origem=Origem.DIARIA,
        destinatarios=(CHAT, CHAT_DO_IRMAO),
        total_de_partes=2,
    )
    # O estado agregado do pedido é INCERTO — é o que `ProcessarPedido._entregar`
    # grava quando qualquer destinatário fica incerto (prioridade mais alta).
    incerta = (
        diaria_compartilhada.reservar("bloco-1")
        .iniciar_envio()
        .marcar_incerto("intenção registrada sem confirmação (destinatário 111222333)")
    )
    repositorio = RepositorioFalso({identidade: incerta})
    # CHAT recebeu tudo; CHAT_DO_IRMAO é quem ficou incerto.
    repositorio.marcar_confirmada(identidade, CHAT, 0)
    repositorio.marcar_confirmada(identidade, CHAT, 1)
    repositorio.marcar_incerta(identidade, CHAT_DO_IRMAO, 0)

    status_de_chat = _consultar(repositorio, chat_id=CHAT).executar()
    status_do_irmao = _consultar(repositorio, chat_id=CHAT_DO_IRMAO).executar()

    assert status_de_chat.situacao_da_diaria_de_hoje.estado is EstadoDoPedido.ENVIADO
    assert status_de_chat.situacao_da_diaria_de_hoje.tem_partes_incertas is False

    assert status_do_irmao.situacao_da_diaria_de_hoje.estado is EstadoDoPedido.INCERTO
    assert status_do_irmao.situacao_da_diaria_de_hoje.tem_partes_incertas is True


def test_destinatario_que_recebeu_tudo_e_reportado_como_enviado_quando_o_pedido_teve_sucesso() -> (
    None
):
    """Quando o pedido inteiro concluiu (todos os destinatários), cada um vê
    o próprio sucesso — não há ambiguidade a resolver neste caso."""
    identidade = Pedido.identidade_de_diaria(HOJE)
    diaria_compartilhada = Pedido(
        identidade=identidade,
        origem=Origem.DIARIA,
        destinatarios=(CHAT, CHAT_DO_IRMAO),
        total_de_partes=2,
    )
    concluida = diaria_compartilhada.reservar("bloco-1").iniciar_envio().concluir()
    repositorio = RepositorioFalso({identidade: concluida})

    status_de_chat = _consultar(repositorio, chat_id=CHAT).executar()
    status_do_irmao = _consultar(repositorio, chat_id=CHAT_DO_IRMAO).executar()

    assert status_de_chat.situacao_da_diaria_de_hoje.estado is EstadoDoPedido.ENVIADO
    assert status_do_irmao.situacao_da_diaria_de_hoje.estado is EstadoDoPedido.ENVIADO


def test_destinatario_sem_nenhuma_parte_recebida_nao_ve_parcial_so_por_causa_do_outro() -> None:
    """Quem não recebeu nada não herda a entrega parcial de outro destinatário."""
    identidade = Pedido.identidade_de_diaria(HOJE)
    diaria_compartilhada = Pedido(
        identidade=identidade,
        origem=Origem.DIARIA,
        destinatarios=(CHAT, CHAT_DO_IRMAO),
        total_de_partes=2,
    )
    # CHAT confirmou algo antes do pedido falhar; o agregado vira PARCIAL.
    parcial = (
        diaria_compartilhada.reservar("bloco-1")
        .iniciar_envio()
        .falhar(alguma_parte_enviada=True, motivo="Bot API respondeu HTTP 403 para um destinatário")
    )
    repositorio = RepositorioFalso({identidade: parcial})
    repositorio.marcar_confirmada(identidade, CHAT, 0)
    # CHAT_DO_IRMAO não tem nenhuma parte confirmada nem incerta registrada.

    status_de_chat = _consultar(repositorio, chat_id=CHAT).executar()
    status_do_irmao = _consultar(repositorio, chat_id=CHAT_DO_IRMAO).executar()

    assert status_de_chat.situacao_da_diaria_de_hoje.estado is EstadoDoPedido.PARCIAL
    assert status_do_irmao.situacao_da_diaria_de_hoje.estado is EstadoDoPedido.FALHOU
    # E não deve aparecer como "último envio" de quem não recebeu nada.
    assert status_do_irmao.ultimo_envio is None


def test_destinatario_sem_nenhuma_parte_recebida_nao_ve_incerto_so_por_causa_do_outro() -> None:
    """Uma incerteza alheia não transforma a falha própria em entrega incerta."""
    identidade = Pedido.identidade_de_diaria(HOJE)
    diaria_compartilhada = Pedido(
        identidade=identidade,
        origem=Origem.DIARIA,
        destinatarios=(CHAT, CHAT_DO_IRMAO),
        total_de_partes=2,
    )
    # CHAT ficou incerto (prioridade mais alta que falhou); o agregado vira
    # INCERTO mesmo que CHAT_DO_IRMAO tenha simplesmente falhado sem nada.
    incerta = (
        diaria_compartilhada.reservar("bloco-1")
        .iniciar_envio()
        .marcar_incerto("Telegram pode ter aceitado a parte")
    )
    repositorio = RepositorioFalso({identidade: incerta})
    repositorio.marcar_incerta(identidade, CHAT, 0)
    # CHAT_DO_IRMAO não tem nenhuma parte confirmada nem incerta registrada —
    # ele falhou de verdade, sem nenhuma ambiguidade própria.

    status_de_chat = _consultar(repositorio, chat_id=CHAT).executar()
    status_do_irmao = _consultar(repositorio, chat_id=CHAT_DO_IRMAO).executar()

    assert status_de_chat.situacao_da_diaria_de_hoje.estado is EstadoDoPedido.INCERTO
    assert status_de_chat.situacao_da_diaria_de_hoje.tem_partes_incertas is True

    assert status_do_irmao.situacao_da_diaria_de_hoje.estado is EstadoDoPedido.FALHOU
    assert status_do_irmao.situacao_da_diaria_de_hoje.tem_partes_incertas is False


def test_motivo_de_pedido_compartilhado_nao_vaza_dados_de_outro_destinatario() -> None:
    """O motivo agregado pode conter dados alheios, ausentes na resposta individual."""
    identidade = Pedido.identidade_de_diaria(HOJE)
    diaria_compartilhada = Pedido(
        identidade=identidade,
        origem=Origem.DIARIA,
        destinatarios=(CHAT, CHAT_DO_IRMAO),
        total_de_partes=2,
    )
    # Motivo no formato real que `ProcessarPedido._motivo_agregado` produziria
    # para um pedido com vários destinatários — menciona o chat_id do irmão.
    motivo_com_chat_id_do_irmao = (
        f"Telegram pode ter aceitado a parte, mas não houve confirmação durável "
        f"(destinatário {CHAT_DO_IRMAO})"
    )
    incerta = (
        diaria_compartilhada.reservar("bloco-1")
        .iniciar_envio()
        .marcar_incerto(motivo_com_chat_id_do_irmao)
    )
    repositorio = RepositorioFalso({identidade: incerta})
    repositorio.marcar_confirmada(identidade, CHAT, 0)
    repositorio.marcar_incerta(identidade, CHAT_DO_IRMAO, 0)

    status_de_chat = _consultar(repositorio, chat_id=CHAT).executar()

    motivo = status_de_chat.situacao_da_diaria_de_hoje.motivo
    assert motivo is not None
    assert str(CHAT_DO_IRMAO) not in motivo
    assert "destinatário" not in motivo


def test_incerteza_propria_independe_de_retentativas_de_outro_destinatario() -> None:
    identidade = Pedido.identidade_de_diaria(HOJE)
    diaria_compartilhada = Pedido(
        identidade=identidade,
        origem=Origem.DIARIA,
        destinatarios=(CHAT, CHAT_DO_IRMAO),
        total_de_partes=2,
    )
    # CHAT_DO_IRMAO teve erro transitório: o pedido inteiro aguarda nova
    # tentativa, mesmo que CHAT já tenha uma parte incerta persistida.
    aguardando = (
        diaria_compartilhada.reservar("bloco-1")
        .iniciar_envio()
        .aguardar_tentativa("Bot API respondeu HTTP 500 (destinatário 111222333)")
    )
    repositorio = RepositorioFalso({identidade: aguardando})
    repositorio.marcar_incerta(identidade, CHAT, 0)

    status_de_chat = _consultar(repositorio, chat_id=CHAT).executar()

    assert status_de_chat.situacao_da_diaria_de_hoje.estado is EstadoDoPedido.INCERTO
    assert status_de_chat.situacao_da_diaria_de_hoje.tem_partes_incertas is True
    motivo = status_de_chat.situacao_da_diaria_de_hoje.motivo
    assert motivo is not None
    assert str(CHAT_DO_IRMAO) not in motivo


# --- último envio ---------------------------------------------------------------


def test_ultimo_envio_e_a_diaria_de_hoje_quando_ja_entregue() -> None:
    identidade = Pedido.identidade_de_diaria(HOJE)
    repositorio = RepositorioFalso({identidade: _diaria(HOJE, "enviado")})

    relatorio = _consultar(repositorio).executar()

    assert relatorio.ultimo_envio is not None
    assert relatorio.ultimo_envio.dia == HOJE
    assert relatorio.ultimo_envio.estado is EstadoDoPedido.ENVIADO


def test_ultimo_envio_recua_para_ontem_quando_hoje_falhou() -> None:
    ontem = HOJE - timedelta(days=1)
    identidade_de_ontem = Pedido.identidade_de_diaria(ontem)
    repositorio = RepositorioFalso(
        {
            Pedido.identidade_de_diaria(HOJE): _diaria(HOJE, "falhou"),
            identidade_de_ontem: _diaria(ontem, "parcial"),
        }
    )
    repositorio.marcar_confirmada(identidade_de_ontem, CHAT, 0)

    relatorio = _consultar(repositorio).executar()

    assert relatorio.ultimo_envio is not None
    assert relatorio.ultimo_envio.dia == ontem
    assert relatorio.ultimo_envio.estado is EstadoDoPedido.PARCIAL


def test_ultimo_envio_recua_para_ontem_quando_hoje_ainda_nao_existe() -> None:
    ontem = HOJE - timedelta(days=1)
    repositorio = RepositorioFalso({Pedido.identidade_de_diaria(ontem): _diaria(ontem, "enviado")})

    relatorio = _consultar(repositorio).executar()

    assert relatorio.ultimo_envio is not None
    assert relatorio.ultimo_envio.dia == ontem


def test_ultimo_envio_de_ontem_no_formato_anterior_a_v2_ainda_e_encontrado() -> None:
    """Achado do code-review: no dia da publicação da v2, a diária de ontem
    ainda está gravada como `diaria#<chat_id>#<dia>` (formato anterior)."""
    ontem = HOJE - timedelta(days=1)
    diaria_no_formato_antigo = _diaria(ontem, "enviado")
    repositorio = RepositorioFalso({f"diaria#{CHAT}#{ontem.isoformat()}": diaria_no_formato_antigo})

    relatorio = _consultar(repositorio).executar()

    assert relatorio.ultimo_envio is not None
    assert relatorio.ultimo_envio.dia == ontem
    assert relatorio.ultimo_envio.estado is EstadoDoPedido.ENVIADO


def test_ultimo_envio_e_none_quando_nem_hoje_nem_ontem_foram_entregues() -> None:
    ontem = HOJE - timedelta(days=1)
    repositorio = RepositorioFalso(
        {
            Pedido.identidade_de_diaria(HOJE): _diaria(HOJE, "falhou"),
            Pedido.identidade_de_diaria(ontem): _diaria(ontem, "falhou"),
        }
    )

    relatorio = _consultar(repositorio).executar()

    assert relatorio.ultimo_envio is None


def test_ultimo_envio_de_ontem_tambem_reflete_o_destinatario_quando_compartilhado() -> None:
    """A diária de ontem também usa as confirmações próprias de quem consulta."""
    ontem = HOJE - timedelta(days=1)
    identidade_de_ontem = Pedido.identidade_de_diaria(ontem)
    diaria_de_ontem_compartilhada = Pedido(
        identidade=identidade_de_ontem,
        origem=Origem.DIARIA,
        destinatarios=(CHAT, CHAT_DO_IRMAO),
        total_de_partes=2,
    )
    # Uma de duas partes chegou antes da falha.
    parcial = (
        diaria_de_ontem_compartilhada.reservar("bloco-1")
        .iniciar_envio()
        .falhar(alguma_parte_enviada=True, motivo="Bot API respondeu HTTP 403")
    )
    repositorio = RepositorioFalso({identidade_de_ontem: parcial})
    repositorio.marcar_confirmada(identidade_de_ontem, CHAT, 0)
    # CHAT_DO_IRMAO não tem nenhuma parte confirmada nem incerta.

    ultimo_envio_de_chat = _consultar(repositorio, chat_id=CHAT).executar().ultimo_envio
    ultimo_envio_do_irmao = _consultar(repositorio, chat_id=CHAT_DO_IRMAO).executar().ultimo_envio

    assert ultimo_envio_de_chat is not None
    assert ultimo_envio_de_chat.estado is EstadoDoPedido.PARCIAL
    # CHAT_DO_IRMAO não recebeu nada ontem: não conta como "último envio" dele.
    assert ultimo_envio_do_irmao is None


# --- próxima ocorrência diária --------------------------------------------------


def test_proxima_ocorrencia_e_hoje_quando_a_diaria_de_hoje_nao_terminou() -> None:
    relatorio = _consultar(RepositorioFalso()).executar()

    assert relatorio.proxima_ocorrencia_diaria == datetime(2026, 9, 7, 11, 0, tzinfo=UTC)


def test_proxima_ocorrencia_e_amanha_quando_a_diaria_de_hoje_ja_terminou() -> None:
    identidade = Pedido.identidade_de_diaria(HOJE)
    repositorio = RepositorioFalso({identidade: _diaria(HOJE, "enviado")})

    relatorio = _consultar(repositorio).executar()

    assert relatorio.proxima_ocorrencia_diaria == datetime(2026, 9, 8, 11, 0, tzinfo=UTC)


# --- sincronização (lê o que já está persistido; nunca sincroniza de novo) ------


def test_sincronizacao_bem_sucedida_sem_cache() -> None:
    colecao = _colecao_valida(usou_cache=False)

    relatorio = _consultar(RepositorioFalso(), colecao).executar()

    assert relatorio.sincronizacao.colecao_disponivel is True
    assert relatorio.sincronizacao.usou_cache is False
    assert relatorio.sincronizacao.erro is None
    assert relatorio.sincronizacao.instante_da_ultima_valida == AGORA


def test_ultima_tentativa_com_erro_indica_uso_de_cache() -> None:
    # A tentativa mais recente falhou (não gerou snapshot novo): o que está
    # ativo só pode ser o cache de uma sincronização anterior.
    colecao = _colecao_valida(usou_cache=True, erro="Notion respondeu HTTP 503")

    relatorio = _consultar(RepositorioFalso(), colecao).executar()

    assert relatorio.sincronizacao.usou_cache is True
    assert relatorio.sincronizacao.erro == "Notion respondeu HTTP 503"
    # O snapshot ativo é mais antigo que a tentativa que falhou.
    valido = relatorio.sincronizacao.instante_da_ultima_valida
    assert valido is not None
    assert valido < AGORA


def test_sincronizacao_sem_nenhuma_colecao_disponivel() -> None:
    colecao = ColecaoFalsa(
        ativa=None,
        tentativa=TentativaDeSincronizacao(instante=AGORA, erro="Notion respondeu HTTP 500"),
    )

    relatorio = _consultar(RepositorioFalso(), colecao).executar()

    assert relatorio.sincronizacao.colecao_disponivel is False
    assert relatorio.sincronizacao.instante_da_ultima_valida is None
    assert relatorio.sincronizacao.erro == "Notion respondeu HTTP 500"


def test_sem_nenhuma_tentativa_registrada_ainda() -> None:
    # Transição: um snapshot já existia antes deste campo existir, e nenhuma
    # sincronização rodou desde então.
    colecao = ColecaoFalsa(
        ativa=SnapshotPersistido(identificador="snap-1", colecao=COLECAO_VAZIA, instante=AGORA),
        tentativa=None,
    )

    relatorio = _consultar(RepositorioFalso(), colecao).executar()

    assert relatorio.sincronizacao.colecao_disponivel is True
    assert relatorio.sincronizacao.usou_cache is False
    assert relatorio.sincronizacao.instante_da_ultima_tentativa == AGORA


def test_nunca_sincronizou_e_sem_nenhuma_colecao() -> None:
    relatorio = _consultar(RepositorioFalso(), ColecaoFalsa()).executar()

    assert relatorio.sincronizacao.colecao_disponivel is False
    assert relatorio.sincronizacao.instante_da_ultima_tentativa is None
    assert relatorio.sincronizacao.erro is None


def test_status_nao_chama_nenhum_metodo_de_sincronizacao_ao_vivo() -> None:
    # ColecaoFalsa só tem carregar_ativa/ultima_tentativa — se ConsultarStatus
    # tentasse sincronizar de verdade, não haveria método para chamar.
    colecao = _colecao_valida()
    assert not hasattr(colecao, "executar")

    _consultar(RepositorioFalso(), colecao).executar()  # não levanta AttributeError


# --- EnviarStatus: consulta, formata e envia -----------------------------------


class CanalEspiao:
    def __init__(self) -> None:
        self.enviados: list[tuple[int, str]] = []

    def enviar_texto(self, chat_id: int, texto: str) -> int:
        self.enviados.append((chat_id, texto))
        return 901


def test_enviar_status_manda_o_relatorio_formatado_para_a_conversa() -> None:
    canal = CanalEspiao()
    consultar = _consultar(RepositorioFalso())

    EnviarStatus(consultar=consultar, canal=canal).executar()

    assert len(canal.enviados) == 1
    chat_id, texto = canal.enviados[0]
    assert chat_id == CHAT
    assert "Próxima ocorrência diária" in texto


@pytest.mark.parametrize("dia", [HOJE, HOJE - timedelta(days=1)])
def test_destinatario_adicionado_depois_nao_herda_entrega_do_pedido(dia: date) -> None:
    pedido = _diaria(dia, "enviado")
    repositorio = RepositorioFalso({pedido.identidade: pedido})

    relatorio = _consultar(repositorio, chat_id=CHAT_DO_IRMAO).executar()

    assert relatorio.situacao_da_diaria_de_hoje.existe is False
    assert relatorio.ultimo_envio is None


@pytest.mark.parametrize("estado", [EstadoDoPedido.PARCIAL, EstadoDoPedido.INCERTO])
def test_historico_legado_individual_preserva_desfecho_sem_metadados_novos(
    estado: EstadoDoPedido,
) -> None:
    ontem = HOJE - timedelta(days=1)
    pedido = replace(
        _diaria(ontem, "enviado"),
        identidade=f"diaria#{CHAT}#{ontem.isoformat()}",
        estado=estado,
    )
    repositorio = RepositorioFalso({pedido.identidade: pedido})

    ultimo = _consultar(repositorio).executar().ultimo_envio

    assert ultimo is not None
    assert ultimo.estado is estado
    assert ultimo.tem_partes_incertas is (estado is EstadoDoPedido.INCERTO)


@pytest.mark.parametrize("destinatarios", [(CHAT,), (CHAT, CHAT_DO_IRMAO)])
def test_resposta_nao_expoe_motivo_bruto_e_mantem_horario_local(
    destinatarios: tuple[int, ...],
) -> None:
    motivo = "token-ficticio https://example.invalid/?assinatura=ficticia parametro-interno"
    pedido = replace(_diaria(HOJE, "falhou"), destinatarios=destinatarios, motivo_do_estado=motivo)
    repositorio = RepositorioFalso({pedido.identidade: pedido})
    canal = CanalEspiao()

    EnviarStatus(_consultar(repositorio), canal).executar()

    destino, texto = canal.enviados[0]
    assert destino == CHAT
    assert "Diária de hoje: falhou" in texto
    assert "Próxima ocorrência diária: 08/09 08:00" in texto
    for proibido in ("token-ficticio", "example.invalid", "assinatura", "parametro-interno"):
        assert proibido not in texto
