"""`/status` monta um retrato do sistema sem consumir frase, tocar o ciclo ou sincronizar.

Por isso `ConsultarStatus` só recebe um repositório de pedidos e um repositório
de coleção, ambos de leitura — nem ciclo, nem reserva, nem um sincronizador de
verdade existem aqui para chamar. Os dados de sincronização vêm do que a
última tentativa real (diária, extra ou reconciliador) já deixou persistido.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from frase_diaria.aplicacao.consultar_status import ConsultarStatus, EnviarStatus
from frase_diaria.dominio.colecao import ColecaoValida, SnapshotPersistido, TentativaDeSincronizacao
from frase_diaria.dominio.pedido import EstadoDoPedido, Origem, Pedido

CHAT = 672024065
HOJE = date(2026, 9, 7)
AGORA = datetime(2026, 9, 7, 13, 0, tzinfo=UTC)  # 10:00 em São Paulo
COLECAO_VAZIA = ColecaoValida(itens=())


class RelogioFixo:
    def agora(self) -> datetime:
        return AGORA


class RepositorioFalso:
    def __init__(self, pedidos: dict[str, Pedido] | None = None) -> None:
        self._pedidos = pedidos or {}
        self._incertas: dict[str, set[int]] = {}

    def obter(self, identidade: str) -> Pedido | None:
        return self._pedidos.get(identidade)

    def marcar_incerta(self, identidade: str, indice: int) -> None:
        self._incertas.setdefault(identidade, set()).add(indice)

    def indices_incertos(self, identidade: str) -> set[int]:
        return self._incertas.get(identidade, set())


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


def _consultar(repositorio: Any, colecao: Any = None) -> ConsultarStatus:
    return ConsultarStatus(
        repositorio=repositorio,
        colecao=colecao if colecao is not None else _colecao_valida(),
        relogio=RelogioFixo(),
        chat_id=CHAT,
    )


def _diaria(dia: date, estado_final: str | None = None) -> Pedido:
    pedido = Pedido(
        identidade=Pedido.identidade_de_diaria(CHAT, dia), origem=Origem.DIARIA, chat_id=CHAT
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
    identidade = Pedido.identidade_de_diaria(CHAT, HOJE)
    repositorio = RepositorioFalso({identidade: _diaria(HOJE)})

    relatorio = _consultar(repositorio).executar()

    assert relatorio.situacao_da_diaria_de_hoje.existe is True
    assert relatorio.situacao_da_diaria_de_hoje.estado is EstadoDoPedido.PENDENTE


def test_diaria_de_hoje_com_partes_incertas() -> None:
    identidade = Pedido.identidade_de_diaria(CHAT, HOJE)
    diaria = (
        _diaria(HOJE)
        .reservar("bloco-1")
        .iniciar_envio()
        .marcar_incerto("Telegram pode ter aceitado")
    )
    repositorio = RepositorioFalso({identidade: diaria})
    repositorio.marcar_incerta(identidade, 0)

    relatorio = _consultar(repositorio).executar()

    assert relatorio.situacao_da_diaria_de_hoje.tem_partes_incertas is True


# --- último envio ---------------------------------------------------------------


def test_ultimo_envio_e_a_diaria_de_hoje_quando_ja_entregue() -> None:
    identidade = Pedido.identidade_de_diaria(CHAT, HOJE)
    repositorio = RepositorioFalso({identidade: _diaria(HOJE, "enviado")})

    relatorio = _consultar(repositorio).executar()

    assert relatorio.ultimo_envio is not None
    assert relatorio.ultimo_envio.dia == HOJE
    assert relatorio.ultimo_envio.estado is EstadoDoPedido.ENVIADO


def test_ultimo_envio_recua_para_ontem_quando_hoje_falhou() -> None:
    ontem = HOJE - timedelta(days=1)
    repositorio = RepositorioFalso(
        {
            Pedido.identidade_de_diaria(CHAT, HOJE): _diaria(HOJE, "falhou"),
            Pedido.identidade_de_diaria(CHAT, ontem): _diaria(ontem, "parcial"),
        }
    )

    relatorio = _consultar(repositorio).executar()

    assert relatorio.ultimo_envio is not None
    assert relatorio.ultimo_envio.dia == ontem
    assert relatorio.ultimo_envio.estado is EstadoDoPedido.PARCIAL


def test_ultimo_envio_recua_para_ontem_quando_hoje_ainda_nao_existe() -> None:
    ontem = HOJE - timedelta(days=1)
    repositorio = RepositorioFalso(
        {Pedido.identidade_de_diaria(CHAT, ontem): _diaria(ontem, "enviado")}
    )

    relatorio = _consultar(repositorio).executar()

    assert relatorio.ultimo_envio is not None
    assert relatorio.ultimo_envio.dia == ontem


def test_ultimo_envio_e_none_quando_nem_hoje_nem_ontem_foram_entregues() -> None:
    ontem = HOJE - timedelta(days=1)
    repositorio = RepositorioFalso(
        {
            Pedido.identidade_de_diaria(CHAT, HOJE): _diaria(HOJE, "falhou"),
            Pedido.identidade_de_diaria(CHAT, ontem): _diaria(ontem, "falhou"),
        }
    )

    relatorio = _consultar(repositorio).executar()

    assert relatorio.ultimo_envio is None


# --- próxima ocorrência diária --------------------------------------------------


def test_proxima_ocorrencia_e_hoje_quando_a_diaria_de_hoje_nao_terminou() -> None:
    relatorio = _consultar(RepositorioFalso()).executar()

    assert relatorio.proxima_ocorrencia_diaria == datetime(2026, 9, 7, 11, 0, tzinfo=UTC)


def test_proxima_ocorrencia_e_amanha_quando_a_diaria_de_hoje_ja_terminou() -> None:
    identidade = Pedido.identidade_de_diaria(CHAT, HOJE)
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
