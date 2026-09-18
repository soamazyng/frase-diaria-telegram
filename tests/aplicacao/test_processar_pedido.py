"""O worker: transforma um pedido persistido em mensagens entregues.

Duas regras governam: o worker lê o pedido da persistência (nunca do corpo de uma
requisição), e uma parte só conta como entregue quando o Telegram confirmou **e**
a confirmação foi persistida.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from frase_diaria.aplicacao.consultar_status import ConsultarStatus
from frase_diaria.aplicacao.encerrar_pedido import (
    ContextoDoEncerramento,
    EncerrarPedido,
    PoliticaDeContencaoDoCiclo,
)
from frase_diaria.aplicacao.entregar_pedido import (
    DesfechoDaEntrega,
    EntregadorDePedido,
    ResultadoDaEntrega,
)
from frase_diaria.aplicacao.portas import (
    ChaveDeParte,
    ClassificacaoDoErroDeEnvio,
    ConfirmacaoDeParte,
    ConflitoDeConcorrencia,
    IncertezaDeParte,
    IntencaoDeParte,
)
from frase_diaria.aplicacao.processar_pedido import ProcessarPedido, ReservaPendente
from frase_diaria.dominio.ciclo import Ciclo
from frase_diaria.dominio.colecao import SnapshotPersistido, TentativaDeSincronizacao
from frase_diaria.dominio.frase import Frase
from frase_diaria.dominio.pedido import EstadoDoPedido, Origem, Pedido
from frase_diaria.telegram.canal import ErroDoTelegram

CHAT = 101
UMA_FRASE = Frase(identidade="bloco-1", partes=("parte um", "parte dois"))
INSTANTE = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def _sem_dispersao(inicio: float, fim: float) -> float:
    del fim
    return inicio


def _erro_transitorio(
    mensagem: str, codigo_http: int | None = None, retry_after_s: float | None = None
) -> ErroDoTelegram:
    return ErroDoTelegram(
        mensagem,
        ClassificacaoDoErroDeEnvio(
            codigo_http=codigo_http,
            retry_after_s=retry_after_s,
            transitorio=True,
        ),
    )


def _erro_ambiguo(mensagem: str) -> ErroDoTelegram:
    return ErroDoTelegram(
        mensagem,
        ClassificacaoDoErroDeEnvio(transitorio=True, resultado_ambiguo=True),
    )


class RelogioFixo:
    def agora(self) -> datetime:
        return INSTANTE


class SorteioPrevisivel:
    def escolher(self, candidatos: Any) -> Any:
        return candidatos[0]


class FonteFixa:
    def __init__(self, frases: tuple[Frase, ...] = (UMA_FRASE,)) -> None:
        self._frases = frases

    def listar(self) -> tuple[Frase, ...]:
        return self._frases


class RepositorioFalso:
    def __init__(self, pedido: Pedido | None) -> None:
        self.pedido = pedido
        self.partes: list[dict[str, Any]] = []
        self.tentativas: list[dict[str, Any]] = []
        self.salvos: list[Pedido] = []
        self.intencoes: list[dict[str, Any]] = []
        self.incertas: list[dict[str, Any]] = []
        self.lease_dono: int | None = None
        self.lease_expira_em: datetime | None = None

    def obter(self, identidade: str) -> Pedido | None:
        return self.pedido

    def assumir_lease(
        self, pedido: str, sequencial: int, agora: datetime, duracao: timedelta
    ) -> None:
        lease_vencido = self.lease_expira_em is not None and agora >= self.lease_expira_em
        if self.lease_dono is not None and sequencial <= self.lease_dono and not lease_vencido:
            raise ConflitoDeConcorrencia("lease do pedido pertence a outro executor")
        self.lease_dono = sequencial
        self.lease_expira_em = agora + duracao

    def _verificar_lease(self, sequencial: int | None) -> None:
        if sequencial is not None and self.lease_dono is not None and sequencial != self.lease_dono:
            raise ConflitoDeConcorrencia("lease do pedido pertence a outro executor")

    def salvar(self, pedido: Pedido, sequencial: int | None = None) -> None:
        self._verificar_lease(sequencial)
        self.pedido = pedido
        self.salvos.append(pedido)

    def registrar_intencao_parte(self, intencao: IntencaoDeParte) -> None:
        self._verificar_lease(intencao.tentativa.sequencial)
        self.intencoes.append(
            {
                "destinatario": intencao.chave.destinatario,
                "indice": intencao.chave.indice,
                "texto": intencao.texto,
            }
        )

    def descartar_intencao_parte(self, chave: ChaveDeParte, sequencial: int) -> None:
        self._verificar_lease(sequencial)
        self.intencoes = [
            parte
            for parte in self.intencoes
            if not (parte["destinatario"] == chave.destinatario and parte["indice"] == chave.indice)
        ]

    def confirmar_parte(self, confirmacao: ConfirmacaoDeParte) -> None:
        self._verificar_lease(confirmacao.tentativa.sequencial)
        self.partes.append(
            {
                "destinatario": confirmacao.chave.destinatario,
                "indice": confirmacao.chave.indice,
                "texto": confirmacao.conteudo.texto,
                "message_id": confirmacao.conteudo.message_id,
            }
        )

    def marcar_parte_incerta(self, incerteza: IncertezaDeParte) -> None:
        self._verificar_lease(incerteza.tentativa.sequencial)
        self.incertas.append(
            {
                "destinatario": incerteza.chave.destinatario,
                "indice": incerteza.chave.indice,
                "motivo": incerteza.motivo,
            }
        )

    def indices_confirmados(self, pedido: str, destinatario: int) -> set[int]:
        return {p["indice"] for p in self.partes if p["destinatario"] == destinatario}

    def indices_incertos(self, pedido: str, destinatario: int) -> set[int]:
        return {p["indice"] for p in self.incertas if p["destinatario"] == destinatario}

    def indices_intencoes(self, pedido: str, destinatario: int) -> set[int]:
        return {p["indice"] for p in self.intencoes if p["destinatario"] == destinatario}

    def ultimo_pedido_do_destinatario(self, destinatario: int, antes_de: Any) -> Pedido | None:
        return None

    def registrar_tentativa(
        self, pedido: str, resultado: str, erro: str | None, instante: Any
    ) -> int:
        self.tentativas.append({"resultado": resultado, "erro": erro})
        return len(self.tentativas)

    def finalizar_tentativa(
        self, pedido: str, sequencial: int, resultado: str, erro: str | None, instante: Any
    ) -> None:
        self.tentativas[sequencial - 1].update(resultado=resultado, erro=erro)


class CanalEspiao:
    def __init__(
        self, falhar_na_parte: int | None = None, erro: ErroDoTelegram | None = None
    ) -> None:
        self.enviados: list[str] = []
        self.falhar_na_parte = falhar_na_parte
        self.erro = erro if erro is not None else ErroDoTelegram("Bot API respondeu HTTP 500")

    def enviar_texto(self, chat_id: int, texto: str) -> int:
        if self.falhar_na_parte is not None and len(self.enviados) == self.falhar_na_parte:
            raise self.erro
        self.enviados.append(texto)
        return 900 + len(self.enviados)


class CanalPorDestinatario:
    """Canal cujo comportamento depende de QUEM está recebendo, não da ordem
    de envio — o que `CanalEspiao` não permite simular."""

    def __init__(self, falha_para: dict[int, ErroDoTelegram] | None = None) -> None:
        self.falha_para = falha_para or {}
        self.enviados: list[tuple[int, str]] = []

    def enviar_texto(self, chat_id: int, texto: str) -> int:
        if chat_id in self.falha_para:
            raise self.falha_para[chat_id]
        self.enviados.append((chat_id, texto))
        return 900 + len(self.enviados)


def _pedido_pendente() -> Pedido:
    return Pedido(identidade="extra#42", origem=Origem.EXTRA, destinatarios=(CHAT,))


class ReservaEmMemoria:
    """Faz o papel da transação: grava ciclo e pedido juntos.

    Se o ciclo perdeu a corrida, a gravação do pedido nem é tentada — a mesma
    atomicidade que a transação real do DynamoDB garante.
    """

    def __init__(self, ciclos: Any, repositorio: Any) -> None:
        self.ciclos = ciclos
        self.repositorio = repositorio

    def efetivar(
        self, pedido: Any, ciclo: Any, versao_anterior_do_ciclo: int, sequencial: int
    ) -> None:
        self.ciclos.salvar(ciclo, versao_anterior_do_ciclo)
        self.repositorio.salvar(pedido, sequencial)


class CiclosEmMemoria:
    def __init__(self, ciclo: Ciclo | None = None, versao: int = 0) -> None:
        self.ciclo = ciclo if ciclo is not None else Ciclo.primeiro()
        self.versao = versao

    def carregar(self) -> tuple[Ciclo, int]:
        return self.ciclo, self.versao

    def salvar(self, ciclo: Ciclo, versao_anterior: int) -> None:
        if versao_anterior != self.versao:
            raise ConflitoDeConcorrencia("ciclo foi alterado por outro executor")
        self.ciclo = ciclo
        self.versao += 1


def _encerrador(repositorio: Any, ciclos: Any) -> EncerrarPedido:
    return EncerrarPedido(
        repositorio,
        ciclos,
        PoliticaDeContencaoDoCiclo(lambda _: None, _sem_dispersao),
    )


def test_encerrador_repetido_conclui_o_pedido_e_consumo_uma_unica_vez() -> None:
    pedido = _pedido_pendente().reservar("bloco-1").iniciar_envio()
    ciclo = Ciclo.primeiro().reservar("bloco-1")
    repositorio = RepositorioFalso(pedido)
    ciclos = CiclosEmMemoria(ciclo)
    encerrador = _encerrador(repositorio, ciclos)
    contexto = ContextoDoEncerramento(ciclo, versao_do_ciclo=0, sequencial=1)
    entrega = ResultadoDaEntrega(pedido, DesfechoDaEntrega.CONCLUIDO, confirmou_algo=True)

    resultado = encerrador.apos_entrega(contexto, entrega)
    resultado_repetido = encerrador.apos_entrega(contexto, entrega)

    assert resultado.estado is EstadoDoPedido.ENVIADO
    assert resultado_repetido.estado is EstadoDoPedido.ENVIADO
    assert ciclos.ciclo.foi_consumida("bloco-1")
    assert ciclos.ciclo.entregas_neste_ciclo == 1
    assert ciclos.versao == 1


def _worker(
    repositorio: Any,
    canal: Any,
    fonte: Any | None = None,
    ciclos: Any | None = None,
) -> ProcessarPedido:
    ciclos = ciclos if ciclos is not None else CiclosEmMemoria()
    relogio = RelogioFixo()
    return ProcessarPedido(
        repositorio=repositorio,
        fonte=fonte if fonte is not None else FonteFixa(),
        entregador=EntregadorDePedido(repositorio, canal, relogio, _sem_dispersao),
        encerrador=_encerrador(repositorio, ciclos),
        sorteio=SorteioPrevisivel(),
        relogio=relogio,
        ciclos=ciclos,
        reserva=ReservaEmMemoria(ciclos, repositorio),
    )


# --- caminho feliz -----------------------------------------------------------


def test_entrega_todas_as_partes_e_conclui() -> None:
    repositorio, canal = RepositorioFalso(_pedido_pendente()), CanalEspiao()

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is not None
    assert canal.enviados == ["parte um", "parte dois"]
    assert resultado.estado is EstadoDoPedido.ENVIADO
    assert resultado.frase_reservada == "bloco-1"


def test_cada_parte_e_confirmada_individualmente_com_o_texto_enviado() -> None:
    repositorio, canal = RepositorioFalso(_pedido_pendente()), CanalEspiao()

    _worker(repositorio, canal).executar("extra#42")

    assert len(repositorio.partes) == 2
    assert repositorio.partes[0] == {
        "destinatario": CHAT,
        "indice": 0,
        "texto": "parte um",
        "message_id": 901,
    }
    assert repositorio.partes[1] == {
        "destinatario": CHAT,
        "indice": 1,
        "texto": "parte dois",
        "message_id": 902,
    }


def test_registra_a_tentativa_bem_sucedida() -> None:
    repositorio, canal = RepositorioFalso(_pedido_pendente()), CanalEspiao()

    _worker(repositorio, canal).executar("extra#42")

    assert repositorio.tentativas[-1]["resultado"] == "enviado"
    assert repositorio.tentativas[-1]["erro"] is None


def test_resposta_ambigua_do_telegram_marca_o_pedido_como_incerto() -> None:
    class CanalAmbiguo:
        def enviar_texto(self, chat_id: int, texto: str) -> int:
            return 0

    repositorio = RepositorioFalso(_pedido_pendente())
    resultado = _worker(repositorio, CanalAmbiguo()).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.INCERTO
    assert resultado.frase_reservada == "bloco-1"
    assert repositorio.incertas == [
        {
            "destinatario": CHAT,
            "indice": 0,
            "motivo": "Telegram pode ter aceitado a parte, mas não houve confirmação durável",
        }
    ]
    assert repositorio.partes == []


def test_intencao_ja_registrada_sem_confirmacao_tambem_persiste_a_incerteza() -> None:
    """Retomar intenção abandonada mantém a ambiguidade visível no histórico."""
    repositorio = RepositorioFalso(_pedido_pendente())
    repositorio.intencoes.append({"destinatario": CHAT, "indice": 0, "texto": "parte um"})

    resultado = _worker(repositorio, CanalEspiao()).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.INCERTO
    assert repositorio.incertas == [
        {
            "destinatario": CHAT,
            "indice": 0,
            "motivo": "intenção registrada sem confirmação; reenvio automático suspenso",
        }
    ]


def test_retomada_de_intencao_antiga_sem_snapshot_suspende_sem_trocar_frase() -> None:
    antigo = replace(
        _pedido_pendente().reservar("bloco-sumida").iniciar_envio(),
        total_de_partes=2,
        partes_reservadas=None,
    )
    repositorio = RepositorioFalso(antigo)
    repositorio.intencoes.append({"destinatario": CHAT, "indice": 0, "texto": "parte um"})
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-sumida"))
    canal = CanalEspiao()

    resultado = _worker(
        repositorio,
        canal,
        fonte=FonteFixa((Frase("bloco-2", ("frase nova",)),)),
        ciclos=ciclos,
    ).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.INCERTO
    assert resultado.frase_reservada == "bloco-sumida"
    assert canal.enviados == []
    assert ciclos.ciclo.foi_consumida("bloco-sumida")
    assert not ciclos.ciclo.foi_consumida("bloco-2")


def test_retomada_apos_converter_intencao_legada_preserva_incerteza() -> None:
    antigo = replace(
        _pedido_pendente().reservar("bloco-sumida").iniciar_envio(),
        total_de_partes=2,
        partes_reservadas=None,
    )
    repositorio = RepositorioFalso(antigo)
    repositorio.incertas.append(
        {"destinatario": CHAT, "indice": 0, "motivo": "conversão interrompida"}
    )
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-sumida"))
    canal = CanalEspiao()

    resultado = _worker(
        repositorio,
        canal,
        fonte=FonteFixa((Frase("bloco-2", ("frase nova",)),)),
        ciclos=ciclos,
    ).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.INCERTO
    assert resultado.frase_reservada == "bloco-sumida"
    assert canal.enviados == []
    assert ciclos.ciclo.foi_consumida("bloco-sumida")


# --- o worker lê da persistência ---------------------------------------------


def test_pedido_inexistente_nao_envia_nada() -> None:
    repositorio, canal = RepositorioFalso(None), CanalEspiao()

    resultado = _worker(repositorio, canal).executar("extra#999")

    assert resultado is None
    assert canal.enviados == []


def test_pedido_ja_concluido_nao_reenvia() -> None:
    concluido = _pedido_pendente().reservar("bloco-1").iniciar_envio().concluir()
    repositorio, canal = RepositorioFalso(concluido), CanalEspiao()

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is not None
    assert canal.enviados == []
    assert resultado is concluido


# --- falhas ------------------------------------------------------------------


def test_falha_na_primeira_parte_libera_a_reserva() -> None:
    repositorio = RepositorioFalso(_pedido_pendente())
    canal = CanalEspiao(falhar_na_parte=0)

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.FALHOU
    assert resultado.frase_reservada is None
    assert repositorio.partes == []


def test_falha_no_meio_mantem_a_frase_consumida_e_o_que_foi_entregue() -> None:
    repositorio = RepositorioFalso(_pedido_pendente())
    canal = CanalEspiao(falhar_na_parte=1)

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.PARCIAL
    assert resultado.frase_reservada == "bloco-1"
    assert len(repositorio.partes) == 1


def test_a_tentativa_falha_guarda_o_erro_sanitizado() -> None:
    repositorio = RepositorioFalso(_pedido_pendente())

    _worker(repositorio, CanalEspiao(falhar_na_parte=0)).executar("extra#42")

    tentativa = repositorio.tentativas[-1]
    assert tentativa["resultado"] == "falhou"
    assert "HTTP 500" in tentativa["erro"]


# --- observabilidade de atraso (ticket 14) ------------------------------------


def test_tentativa_muito_atrasada_e_registrada(caplog: pytest.LogCaptureFixture) -> None:
    atrasado = replace(_pedido_pendente(), proxima_tentativa=INSTANTE - timedelta(minutes=20))
    repositorio = RepositorioFalso(atrasado)

    with caplog.at_level("WARNING"):
        _worker(repositorio, CanalEspiao()).executar("extra#42")

    assert any("atrasada" in registro.message for registro in caplog.records)


def test_tentativa_dentro_do_limite_nao_e_registrada_como_atraso(
    caplog: pytest.LogCaptureFixture,
) -> None:
    no_prazo = replace(_pedido_pendente(), proxima_tentativa=INSTANTE - timedelta(minutes=5))
    repositorio = RepositorioFalso(no_prazo)

    with caplog.at_level("WARNING"):
        _worker(repositorio, CanalEspiao()).executar("extra#42")

    assert not any("atrasada" in registro.message for registro in caplog.records)


# --- retomada ----------------------------------------------------------------


def test_retomada_envia_apenas_as_partes_que_faltam() -> None:
    em_andamento = _pedido_pendente().reservar("bloco-1")
    repositorio = RepositorioFalso(em_andamento)
    repositorio.partes.append(
        {"destinatario": CHAT, "indice": 0, "texto": "parte um", "message_id": 901}
    )
    canal = CanalEspiao()
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-1"))

    _worker(repositorio, canal, ciclos=ciclos).executar("extra#42")

    assert canal.enviados == ["parte dois"]


def test_retomada_parcial_preserva_a_versao_da_frase_que_comecou_a_enviar() -> None:
    em_andamento = replace(
        _pedido_pendente().reservar("bloco-1").iniciar_envio(),
        partes_reservadas=("versão original um", "versão original dois"),
        total_de_partes=2,
    )
    repositorio = RepositorioFalso(em_andamento)
    repositorio.partes.append(
        {
            "destinatario": CHAT,
            "indice": 0,
            "texto": "versão original um",
            "message_id": 901,
        }
    )
    editada = Frase("bloco-1", ("versão editada um", "versão editada dois"))
    canal = CanalEspiao()
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-1"))

    _worker(repositorio, canal, fonte=FonteFixa((editada,)), ciclos=ciclos).executar("extra#42")

    assert canal.enviados == ["versão original dois"]


# --- coleção vazia -----------------------------------------------------------


def test_colecao_vazia_encerra_o_pedido_sem_enviar() -> None:
    repositorio, canal = RepositorioFalso(_pedido_pendente()), CanalEspiao()

    resultado = _worker(repositorio, canal, fonte=FonteFixa(())).executar("extra#42")

    assert resultado is not None
    assert canal.enviados == []
    assert resultado.estado is EstadoDoPedido.FALHOU
    assert "sem frases" in (repositorio.tentativas[-1]["erro"] or "")


def test_a_frase_reservada_e_reaproveitada_em_vez_de_sortear_outra() -> None:
    # Uma nova tentativa reutiliza a reserva existente (spec, 4.4).
    reservado = _pedido_pendente().reservar("bloco-2")
    outra = Frase(identidade="bloco-2", partes=("da reserva",))
    repositorio = RepositorioFalso(reservado)
    canal = CanalEspiao()
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-2"))

    _worker(repositorio, canal, fonte=FonteFixa((UMA_FRASE, outra)), ciclos=ciclos).executar(
        "extra#42"
    )

    assert canal.enviados == ["da reserva"]


# --- falhas inesperadas ------------------------------------------------------


class CanalQueQuebra:
    def enviar_texto(self, chat_id: int, texto: str) -> int:
        raise RuntimeError("boto3 estourou")


def test_erro_inesperado_registra_tentativa_e_propaga() -> None:
    """Propagar é o que permite a Lambda retentar.

    Engolir a exceção deixaria o pedido preso em ENVIANDO, sem tentativa
    registrada e sem ninguém para retomá-lo.
    """
    repositorio = RepositorioFalso(_pedido_pendente())

    with pytest.raises(RuntimeError, match="processamento interrompido"):
        _worker(repositorio, CanalQueQuebra()).executar("extra#42")

    assert repositorio.tentativas[-1]["resultado"] == "erro"
    assert repositorio.tentativas[-1]["erro"] == "erro de integração"


def test_erro_inesperado_loga_o_tipo_da_excecao_sem_a_mensagem(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A mensagem original pode carregar detalhe sensível (URL, corpo de
    resposta); o nome da classe nunca carrega, e já basta pra apontar onde
    investigar sem precisar reproduzir o incidente do zero de novo."""
    repositorio = RepositorioFalso(_pedido_pendente())

    with caplog.at_level("ERROR"), pytest.raises(RuntimeError):
        _worker(repositorio, CanalQueQuebra()).executar("extra#42")

    mensagens = [registro.message for registro in caplog.records]
    assert any("RuntimeError" in mensagem for mensagem in mensagens)
    assert not any("boto3 estourou" in mensagem for mensagem in mensagens)


def test_erro_inesperado_nao_deixa_o_pedido_em_estado_terminal() -> None:
    repositorio = RepositorioFalso(_pedido_pendente())

    with pytest.raises(RuntimeError):
        _worker(repositorio, CanalQueQuebra()).executar("extra#42")

    assert repositorio.pedido is not None
    assert not repositorio.pedido.estado.terminal


class FonteQueQuebra:
    def __init__(self) -> None:
        self.chamadas = 0

    def listar(self) -> tuple[Frase, ...]:
        self.chamadas += 1
        raise RuntimeError("Notion instável")


def test_erro_inesperado_antes_da_entrega_expira_o_pedido_com_prazo_vencido() -> None:
    """Regressão de incidente real: um /frase falhando na sincronização com o
    Notion (antes de qualquer tentativa de entrega) nunca era comparado ao
    prazo — só `EntregadorDePedido` checava isso, e ela nunca era alcançada.
    O pedido reconciliado a cada 5 min por mais de um dia inteiro, com
    centenas de tentativas, todas registrando o mesmo "erro de integração".
    """
    pedido = replace(_pedido_pendente().reservar("bloco-1"), prazo=INSTANTE - timedelta(minutes=1))
    repositorio = RepositorioFalso(pedido)
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-1"))
    fonte = FonteQueQuebra()

    resultado = _worker(repositorio, CanalEspiao(), fonte=fonte, ciclos=ciclos).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.EXPIRADO
    assert fonte.chamadas == 0  # nunca tenta sincronizar um pedido já vencido
    assert ciclos.ciclo.reservadas == frozenset()


def test_erro_inesperado_na_fonte_antes_do_prazo_continua_propagando() -> None:
    """Não regredir: na primeira tentativa, sem prazo vencido, a falha antes
    da entrega ainda propaga para que a Lambda (ou o reconciliador) retente —
    só o prazo, ou uma tentativa única já gasta, encerra o pedido cedo.
    """
    repositorio = RepositorioFalso(_pedido_pendente())

    with pytest.raises(RuntimeError, match="processamento interrompido"):
        _worker(repositorio, CanalEspiao(), fonte=FonteQueQuebra()).executar("extra#42")

    assert repositorio.pedido is not None
    assert not repositorio.pedido.estado.terminal


def test_erro_inesperado_antes_da_entrega_com_prazo_vencido_e_parte_confirmada_vira_parcial() -> (
    None
):
    """`EncerrarPedido.expirar` decide entre EXPIRADO e PARCIAL a partir do que
    já foi confirmado — este é o caminho de retomada (uma parte já entregue
    numa tentativa anterior) encontrando o mesmo erro pré-entrega mascarado.
    """
    pedido = replace(
        _pedido_pendente().reservar("bloco-1").iniciar_envio(),
        prazo=INSTANTE - timedelta(minutes=1),
    )
    repositorio = RepositorioFalso(pedido)
    repositorio.partes.append(
        {"destinatario": CHAT, "indice": 0, "texto": "parte um", "message_id": 901}
    )
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-1"))

    resultado = _worker(repositorio, CanalEspiao(), fonte=FonteQueQuebra(), ciclos=ciclos).executar(
        "extra#42"
    )

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.PARCIAL
    assert resultado.frase_reservada == "bloco-1"
    assert ciclos.ciclo.consumidas_com_ressalva == frozenset({"bloco-1"})


def test_extra_de_tentativa_unica_com_erro_pre_entrega_encerra_na_segunda_tentativa() -> None:
    """Um extra de tentativa única (criado após o meio-dia local) não tem
    `prazo` — a política é "sem retentativa alguma", não "sem limite de tempo"
    (dominio/tempo.py::PoliticaDeExtra). A primeira tentativa ainda precisa
    rodar de verdade (spec, 4.5: "cedo ou tarde"), então um erro pré-entrega
    nela ainda propaga; mas a segunda não pode repetir para sempre.
    """
    pedido = replace(_pedido_pendente(), prazo=None, tentativa_unica=True)
    repositorio = RepositorioFalso(pedido)
    fonte = FonteQueQuebra()

    with pytest.raises(RuntimeError, match="processamento interrompido"):
        _worker(repositorio, CanalEspiao(), fonte=fonte).executar("extra#42")
    assert repositorio.pedido is not None
    assert not repositorio.pedido.estado.terminal
    assert fonte.chamadas == 1

    resultado = _worker(repositorio, CanalEspiao(), fonte=fonte).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.EXPIRADO
    assert fonte.chamadas == 1  # a segunda tentativa nem chega a sincronizar


# --- frase que sumiu da fonte ------------------------------------------------


def test_frase_reservada_sumiu_depois_de_entregar_parte_mantem_a_reserva() -> None:
    """Exclusão na fonte não pode apagar o rastro de uma entrega parcial.

    Liberar a reserva aqui violaria a invariante de que entrega parcial mantém a
    frase consumida — e registraria "sem frases" para um pedido que enviou algo.
    """
    em_andamento = _pedido_pendente().reservar("bloco-sumida").iniciar_envio()
    repositorio = RepositorioFalso(em_andamento)
    repositorio.partes.append(
        {"destinatario": CHAT, "indice": 0, "texto": "já foi", "message_id": 901}
    )
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-sumida"))

    resultado = _worker(repositorio, CanalEspiao(), fonte=FonteFixa(()), ciclos=ciclos).executar(
        "extra#42"
    )

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.PARCIAL
    assert resultado.frase_reservada == "bloco-sumida"


def test_frase_reservada_sumiu_sem_nada_enviado_libera_e_seleciona_outra() -> None:
    # Nada foi entregue ainda: trocar de frase não fere a invariante de entrega
    # lógica única, e o pedido segue em vez de falhar à toa (ticket 11).
    reservado = _pedido_pendente().reservar("bloco-sumida")
    repositorio = RepositorioFalso(reservado)
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-sumida"))
    # A frase reservada não existe mais na fonte; só "bloco-2" está disponível.
    outra = Frase(identidade="bloco-2", partes=("frase nova",))

    resultado = _worker(
        repositorio, CanalEspiao(), fonte=FonteFixa((outra,)), ciclos=ciclos
    ).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.ENVIADO
    assert resultado.frase_reservada == "bloco-2"
    assert ciclos.ciclo.reservadas == frozenset()
    assert ciclos.ciclo.foi_consumida("bloco-2")
    assert not ciclos.ciclo.foi_consumida("bloco-sumida")


def test_frase_reservada_sumiu_sem_alternativa_ainda_falha() -> None:
    # Sem nenhuma frase elegível para trocar, o desfecho continua sendo falha
    # — igual a uma coleção genuinamente vazia.
    reservado = _pedido_pendente().reservar("bloco-sumida")
    repositorio = RepositorioFalso(reservado)
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-sumida"))

    resultado = _worker(repositorio, CanalEspiao(), fonte=FonteFixa(()), ciclos=ciclos).executar(
        "extra#42"
    )

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.FALHOU
    assert resultado.frase_reservada is None


# --- ciclo atravessando as camadas -------------------------------------------

COLECAO = tuple(Frase(identidade=f"f{n}", partes=(f"frase {n}",)) for n in range(1, 4))


class SorteioDoUltimo:
    def escolher(self, candidatos: Any) -> Any:
        return candidatos[-1]


def _entregar_uma(ciclos: Any, update_id: int, sorteio: Any = None) -> str:
    """Roda um pedido inteiro e devolve o texto entregue."""
    repositorio = RepositorioFalso(
        Pedido(identidade=f"extra#{update_id}", origem=Origem.EXTRA, destinatarios=(CHAT,))
    )
    canal = CanalEspiao()
    relogio = RelogioFixo()
    worker = ProcessarPedido(
        repositorio=repositorio,
        fonte=FonteFixa(COLECAO),
        entregador=EntregadorDePedido(repositorio, canal, relogio, _sem_dispersao),
        encerrador=_encerrador(repositorio, ciclos),
        sorteio=sorteio if sorteio is not None else SorteioPrevisivel(),
        relogio=relogio,
        ciclos=ciclos,
        reserva=ReservaEmMemoria(ciclos, repositorio),
    )
    worker.executar(f"extra#{update_id}")
    return canal.enviados[0]


def test_tres_pedidos_seguidos_entregam_as_tres_frases_sem_repetir() -> None:
    """AC04, ponta a ponta: com N frases, N entregas têm identidades distintas."""
    ciclos = CiclosEmMemoria()

    entregues = [_entregar_uma(ciclos, n) for n in range(1, 4)]

    assert sorted(entregues) == ["frase 1", "frase 2", "frase 3"]


def test_a_quarta_entrega_abre_ciclo_novo_sem_repetir_a_ultima() -> None:
    """AC05: a primeira do ciclo novo difere da última do anterior."""
    ciclos = CiclosEmMemoria()
    for n in range(1, 4):
        _entregar_uma(ciclos, n, sorteio=SorteioDoUltimo())
    ultima = ciclos.ciclo.ultima_entregue
    assert ultima is not None

    quarta = _entregar_uma(ciclos, 4, sorteio=SorteioDoUltimo())

    assert ciclos.ciclo.numero == 2
    assert quarta != f"frase {ultima[1:]}"


def test_o_consumo_so_e_marcado_apos_a_entrega_confirmada() -> None:
    ciclos = CiclosEmMemoria()
    repositorio = RepositorioFalso(_pedido_pendente())

    _worker(repositorio, CanalEspiao(falhar_na_parte=0), ciclos=ciclos).executar("extra#42")

    # Nada foi entregue: a frase volta às elegíveis, sem consumo.
    assert ciclos.ciclo.consumidas == frozenset()
    assert ciclos.ciclo.reservadas == frozenset()


def test_entrega_parcial_consome_a_frase_com_ressalva() -> None:
    ciclos = CiclosEmMemoria()
    repositorio = RepositorioFalso(_pedido_pendente())

    _worker(repositorio, CanalEspiao(falhar_na_parte=1), ciclos=ciclos).executar("extra#42")

    assert ciclos.ciclo.foi_consumida("bloco-1")
    assert ciclos.ciclo.consumidas_com_ressalva == frozenset({"bloco-1"})


def test_entrega_completa_consome_sem_ressalva() -> None:
    ciclos = CiclosEmMemoria()
    repositorio = RepositorioFalso(_pedido_pendente())

    _worker(repositorio, CanalEspiao(), ciclos=ciclos).executar("extra#42")

    assert ciclos.ciclo.foi_consumida("bloco-1")
    assert ciclos.ciclo.consumidas_com_ressalva == frozenset()


class CiclosQueContamGravacoes(CiclosEmMemoria):
    def __init__(self, ciclo: Ciclo | None = None) -> None:
        super().__init__(ciclo)
        self.chamadas = 0

    def salvar(self, ciclo: Ciclo, versao_anterior: int) -> None:
        self.chamadas += 1
        super().salvar(ciclo, versao_anterior)


def test_reservar_e_entregar_na_mesma_execucao_nao_gera_conflito_de_versao() -> None:
    # Regressão (achado do code-review): sem avançar `versao_ciclo` em memória
    # logo depois que `reserva.efetivar` persiste a versão seguinte, o consumo
    # tentaria gravar com a versão já superada e cairia na retentativa por
    # engano — mesmo sem nenhuma concorrência real, em toda entrega comum.
    ciclos = CiclosQueContamGravacoes()
    repositorio = RepositorioFalso(_pedido_pendente())

    _worker(repositorio, CanalEspiao(), ciclos=ciclos).executar("extra#42")

    assert ciclos.chamadas == 2


# --- correções vindas do code-review -----------------------------------------


def test_todas_reservadas_propaga_em_vez_de_encerrar() -> None:
    """Condição transitória não pode virar estado terminal.

    Se a diária encontrasse a última frase reservada por um `/frase` em curso e
    encerrasse, nem a retomada nem a janela até 12:00 a reabririam.
    """
    ciclo = Ciclo.primeiro()
    for frase in ("f1", "f2"):
        ciclo = ciclo.reservar(frase).consumir(frase)
    ciclo = ciclo.reservar("f3")
    ciclos = CiclosEmMemoria(ciclo)
    repositorio = RepositorioFalso(_pedido_pendente())

    with pytest.raises(ReservaPendente):
        _worker(repositorio, CanalEspiao(), fonte=FonteFixa(COLECAO), ciclos=ciclos).executar(
            "extra#42"
        )

    assert repositorio.pedido is not None
    assert not repositorio.pedido.estado.terminal
    assert repositorio.tentativas[-1]["resultado"] == "aguardando"


def test_frase_entregue_e_consumida_mesmo_se_o_ciclo_perdeu_a_reserva() -> None:
    """Pular o consumo em silêncio deixaria a frase elegível de novo no ciclo.

    A mensagem foi para a usuária; o ciclo precisa refletir isso, ainda que uma
    gravação concorrente tenha apagado a reserva.
    """
    reservado = _pedido_pendente().reservar("bloco-1")
    repositorio = RepositorioFalso(reservado)
    ciclos = CiclosEmMemoria(Ciclo.primeiro())  # ciclo sem a reserva

    _worker(repositorio, CanalEspiao(), ciclos=ciclos).executar("extra#42")

    assert ciclos.ciclo.foi_consumida("bloco-1")


def test_o_pedido_e_gravado_antes_do_ciclo_ao_encerrar() -> None:
    # A ordem importa: um crash entre as duas gravações deve deixar o ciclo
    # desatualizado (recuperável), nunca o pedido reivindicando uma reserva que
    # o ciclo já soltou.
    ordem: list[str] = []

    class RepositorioQueAnota(RepositorioFalso):
        def salvar(self, pedido: Any, sequencial: int | None = None) -> None:
            ordem.append("pedido")
            super().salvar(pedido, sequencial)

    class CiclosQueAnotam(CiclosEmMemoria):
        def salvar(self, ciclo: Any, versao_anterior: int) -> None:
            ordem.append("ciclo")
            super().salvar(ciclo, versao_anterior)

    reservado = _pedido_pendente().reservar("bloco-1")
    repositorio = RepositorioQueAnota(reservado)
    ciclos = CiclosQueAnotam(Ciclo.primeiro().reservar("bloco-1"))

    _worker(repositorio, CanalEspiao(falhar_na_parte=0), ciclos=ciclos).executar("extra#42")

    assert ordem[-2:] == ["pedido", "ciclo"]


def test_tentativa_e_duravel_antes_de_ler_a_fonte() -> None:
    repositorio = RepositorioFalso(_pedido_pendente())

    class FonteInterrompida:
        def listar(self) -> tuple[Frase, ...]:
            assert repositorio.tentativas == [{"resultado": "iniciada", "erro": None}]
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _worker(repositorio, CanalEspiao(), fonte=FonteInterrompida()).executar("extra#42")

    assert len(repositorio.tentativas) == 1


# --- lease e concorrência (ticket 09) -----------------------------------------


def test_lease_de_outro_executor_aborta_sem_tocar_o_pedido() -> None:
    # Um sequencial mais novo já assumiu o lease — o mesmo evento entregue duas
    # vezes pela invocação assíncrona da Lambda, por exemplo. Esta execução
    # encerra sem disputar um estado que já não é seu (AC03).
    pendente = _pedido_pendente()
    repositorio = RepositorioFalso(pendente)
    repositorio.lease_dono = 5
    repositorio.lease_expira_em = INSTANTE + timedelta(minutes=10)
    canal = CanalEspiao()

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is pendente
    assert canal.enviados == []
    assert repositorio.salvos == []
    assert repositorio.tentativas[-1]["resultado"] == "aguardando"


class ReservaQueRecusaAPrimeira:
    """Simula dois executores disputando a mesma versão do ciclo."""

    def __init__(self, ciclos: Any, repositorio: Any) -> None:
        self.ciclos = ciclos
        self.repositorio = repositorio
        self.chamadas = 0

    def efetivar(
        self, pedido: Any, ciclo: Any, versao_anterior_do_ciclo: int, sequencial: int
    ) -> None:
        self.chamadas += 1
        if self.chamadas == 1:
            raise ConflitoDeConcorrencia("ciclo foi alterado por outro executor")
        self.ciclos.salvar(ciclo, versao_anterior_do_ciclo)
        self.repositorio.salvar(pedido, sequencial)


def test_conflito_ao_reservar_propaga_como_reserva_pendente() -> None:
    # Uma nova tentativa relê o ciclo do zero em vez de tentar de novo no lugar:
    # a frase sorteada pode já não ser a melhor escolha.
    repositorio = RepositorioFalso(_pedido_pendente())
    ciclos = CiclosEmMemoria()
    reserva = ReservaQueRecusaAPrimeira(ciclos, repositorio)
    relogio = RelogioFixo()
    worker = ProcessarPedido(
        repositorio=repositorio,
        fonte=FonteFixa(),
        entregador=EntregadorDePedido(repositorio, CanalEspiao(), relogio, _sem_dispersao),
        encerrador=_encerrador(repositorio, ciclos),
        sorteio=SorteioPrevisivel(),
        relogio=relogio,
        ciclos=ciclos,
        reserva=reserva,
    )

    with pytest.raises(ReservaPendente):
        worker.executar("extra#42")

    assert repositorio.pedido is not None
    assert not repositorio.pedido.estado.terminal
    assert repositorio.pedido.frase_reservada is None
    assert repositorio.tentativas[-1]["resultado"] == "aguardando"


def test_conflito_ao_trocar_de_frase_nao_orfaniza_a_reserva_antiga_no_ciclo() -> None:
    # Regressão (achado do code-review): se a transação que liberaria a frase
    # antiga e reservaria a nova for recusada, gravar o pedido sem frase
    # reservada mesmo assim deixaria o ciclo com uma reserva que nenhum pedido
    # mais referencia — nada nunca mais a libera, travando o ciclo para sempre.
    reservado = _pedido_pendente().reservar("bloco-sumida")
    repositorio = RepositorioFalso(reservado)
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-sumida"))
    reserva = ReservaQueRecusaAPrimeira(ciclos, repositorio)
    outra = Frase(identidade="bloco-2", partes=("frase nova",))
    relogio = RelogioFixo()
    worker = ProcessarPedido(
        repositorio=repositorio,
        fonte=FonteFixa((outra,)),
        entregador=EntregadorDePedido(repositorio, CanalEspiao(), relogio, _sem_dispersao),
        encerrador=_encerrador(repositorio, ciclos),
        sorteio=SorteioPrevisivel(),
        relogio=relogio,
        ciclos=ciclos,
        reserva=reserva,
    )

    with pytest.raises(ReservaPendente):
        worker.executar("extra#42")

    # O pedido persistido ainda referencia a frase antiga — a mesma que o
    # ciclo persistido continua reservando — para que a próxima tentativa
    # retome a troca em vez de deixar a reserva sem dono.
    assert repositorio.pedido is not None
    assert repositorio.pedido.frase_reservada == "bloco-sumida"
    assert ciclos.ciclo.reservadas == frozenset({"bloco-sumida"})


class CiclosComConflitoAoConsumir(CiclosEmMemoria):
    """A gravação da reserva (1ª chamada) vence; a do consumo (2ª) perde a
    corrida uma vez e só vence ao reler e tentar de novo (3ª chamada)."""

    def __init__(self, ciclo: Ciclo | None = None) -> None:
        super().__init__(ciclo)
        self.chamadas = 0

    def salvar(self, ciclo: Ciclo, versao_anterior: int) -> None:
        self.chamadas += 1
        if self.chamadas == 2:
            raise ConflitoDeConcorrencia("ciclo foi alterado por outro executor")
        super().salvar(ciclo, versao_anterior)


def test_lease_perdido_no_meio_do_envio_abandona_sem_reenviar() -> None:
    # Um sequencial mais novo assumiu o lease depois que esta execução já tinha
    # começado a enviar: a confirmação da parte seguinte é recusada, e a
    # execução superada devolve o pedido como leu no início, sem reenviar nada.
    pendente = _pedido_pendente()
    repositorio = RepositorioFalso(pendente)
    canal = CanalEspiao()
    worker = _worker(repositorio, canal)

    original_confirmar = repositorio.confirmar_parte

    def confirmar_e_perder_o_lease(*args: Any, **kwargs: Any) -> None:
        repositorio.lease_dono = 999  # outro executor assumiu o lease
        original_confirmar(*args, **kwargs)

    repositorio.confirmar_parte = confirmar_e_perder_o_lease  # type: ignore[method-assign]

    resultado = worker.executar("extra#42")

    assert resultado is pendente
    assert repositorio.tentativas[-1]["resultado"] == "superado"


# --- janela e retentativa (ticket 14) -----------------------------------------


def test_erro_transitorio_agenda_nova_tentativa_em_vez_de_falhar() -> None:
    repositorio = RepositorioFalso(_pedido_pendente())
    erro = _erro_transitorio("Bot API respondeu HTTP 500", codigo_http=500)
    canal = CanalEspiao(falhar_na_parte=0, erro=erro)

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.AGUARDANDO_TENTATIVA
    assert resultado.frase_reservada == "bloco-1"  # a reserva não é liberada
    assert resultado.proxima_tentativa is not None
    assert resultado.proxima_tentativa > INSTANTE
    assert repositorio.intencoes == []


def test_erro_transitorio_definitivamente_recusado_tenta_a_mesma_parte_de_novo() -> None:
    repositorio = RepositorioFalso(_pedido_pendente())
    ciclos = CiclosEmMemoria()
    erro = _erro_transitorio("Bot API respondeu HTTP 500", codigo_http=500)

    primeiro = _worker(
        repositorio,
        CanalEspiao(falhar_na_parte=0, erro=erro),
        ciclos=ciclos,
    ).executar("extra#42")

    assert primeiro is not None
    assert primeiro.estado is EstadoDoPedido.AGUARDANDO_TENTATIVA
    assert repositorio.intencoes == []
    repositorio.pedido = replace(primeiro, proxima_tentativa=INSTANTE)

    canal_recuperado = CanalEspiao()
    segundo = _worker(repositorio, canal_recuperado, ciclos=ciclos).executar("extra#42")

    assert segundo is not None
    assert segundo.estado is EstadoDoPedido.ENVIADO
    assert canal_recuperado.enviados == ["parte um", "parte dois"]


def test_falha_ambigua_de_rede_nao_e_reenviada_automaticamente() -> None:
    repositorio = RepositorioFalso(_pedido_pendente())
    erro = _erro_ambiguo("falha de rede ao chamar a Bot API")

    resultado = _worker(
        repositorio,
        CanalEspiao(falhar_na_parte=0, erro=erro),
    ).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.INCERTO
    assert repositorio.indices_incertos("extra#42", CHAT) == {0}


def test_falha_ambigua_de_um_destinatario_nao_interrompe_o_outro() -> None:
    repositorio = RepositorioFalso(_diaria_compartilhada())
    erro = _erro_ambiguo("conexão encerrada sem resposta da Bot API")
    canal = CanalPorDestinatario(falha_para={CHAT: erro})

    resultado = _worker(repositorio, canal).executar("diaria#2026-09-07")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.INCERTO
    assert (CHAT_DO_IRMAO, "parte um") in canal.enviados
    assert (CHAT_DO_IRMAO, "parte dois") in canal.enviados


def test_erro_transitorio_respeita_o_retry_after_do_telegram() -> None:
    repositorio = RepositorioFalso(_pedido_pendente())
    erro = _erro_transitorio("Bot API recusou: 429", retry_after_s=7)
    canal = CanalEspiao(falhar_na_parte=0, erro=erro)

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is not None
    assert resultado.proxima_tentativa == INSTANTE + timedelta(seconds=7)


def test_erro_transitorio_apos_o_prazo_encerra_em_vez_de_retentar() -> None:
    pedido = replace(_pedido_pendente(), prazo=INSTANTE - timedelta(minutes=1))
    repositorio = RepositorioFalso(pedido)
    erro = _erro_transitorio("Bot API respondeu HTTP 500")
    canal = CanalEspiao(falhar_na_parte=0, erro=erro)

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is not None
    assert resultado.estado.terminal
    assert resultado.estado is not EstadoDoPedido.AGUARDANDO_TENTATIVA


def test_erro_permanente_continua_terminal_mesmo_com_prazo_no_futuro() -> None:
    # Regressão: um erro permanente não deve virar retentativa só porque ainda
    # há tempo na janela — a distinção é o tipo do erro, não o relógio (AC13).
    pedido = replace(_pedido_pendente(), prazo=INSTANTE + timedelta(hours=1))
    repositorio = RepositorioFalso(pedido)
    canal = CanalEspiao(falhar_na_parte=0)  # erro padrão: transitorio=False

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.FALHOU


def test_prazo_esgotado_antes_de_qualquer_envio_expira_o_pedido() -> None:
    pedido = replace(_pedido_pendente().reservar("bloco-1"), prazo=INSTANTE - timedelta(minutes=1))
    repositorio = RepositorioFalso(pedido)
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-1"))
    canal = CanalEspiao()

    resultado = _worker(repositorio, canal, ciclos=ciclos).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.EXPIRADO
    assert resultado.frase_reservada is None
    assert canal.enviados == []
    assert ciclos.ciclo.reservadas == frozenset()


def test_prazo_esgotado_com_parte_ja_enviada_vira_parcial() -> None:
    pedido = replace(
        _pedido_pendente().reservar("bloco-1").iniciar_envio(),
        prazo=INSTANTE - timedelta(minutes=1),
    )
    repositorio = RepositorioFalso(pedido)
    repositorio.partes.append(
        {"destinatario": CHAT, "indice": 0, "texto": "parte um", "message_id": 901}
    )
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-1"))
    canal = CanalEspiao()

    resultado = _worker(repositorio, canal, ciclos=ciclos).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.PARCIAL
    assert resultado.frase_reservada == "bloco-1"
    assert canal.enviados == []  # a janela fechou antes de tentar a parte restante
    assert ciclos.ciclo.foi_consumida("bloco-1")
    assert ciclos.ciclo.consumidas_com_ressalva == frozenset({"bloco-1"})


def test_prazo_e_checado_por_parte_nao_so_uma_vez_por_execucao() -> None:
    """Regressão: uma frase de duas partes pode atravessar o prazo no meio do envio.

    O relógio avança a partir do envio da primeira parte (estado observável do
    canal-espião, não uma contagem de chamadas): a checagem antes da segunda
    parte já encontra o prazo vencido, mesmo a tentativa tendo começado dentro
    da janela (CLAUDE.md: checar antes de CADA chamada ao Telegram).
    """

    class CanalQueAtrasaAposEnviar:
        def __init__(self) -> None:
            self.enviados: list[str] = []

        def enviar_texto(self, chat_id: int, texto: str) -> int:
            self.enviados.append(texto)
            return 900 + len(self.enviados)

    class RelogioQueAvancaAposUmEnvio:
        def __init__(self, canal: CanalQueAtrasaAposEnviar) -> None:
            self._canal = canal

        def agora(self) -> datetime:
            return INSTANTE if not self._canal.enviados else INSTANTE + timedelta(minutes=5)

    pedido = replace(_pedido_pendente(), prazo=INSTANTE + timedelta(minutes=1))
    repositorio = RepositorioFalso(pedido)
    ciclos = CiclosEmMemoria()
    canal = CanalQueAtrasaAposEnviar()
    relogio = RelogioQueAvancaAposUmEnvio(canal)
    worker = ProcessarPedido(
        repositorio=repositorio,
        fonte=FonteFixa(),
        entregador=EntregadorDePedido(repositorio, canal, relogio, _sem_dispersao),
        encerrador=_encerrador(repositorio, ciclos),
        sorteio=SorteioPrevisivel(),
        relogio=relogio,
        ciclos=ciclos,
        reserva=ReservaEmMemoria(ciclos, repositorio),
    )

    resultado = worker.executar("extra#42")

    assert resultado is not None
    assert canal.enviados == ["parte um"]  # a segunda parte nunca foi tentada
    assert resultado.estado is EstadoDoPedido.PARCIAL


# --- extra de tentativa única (ticket 14) --------------------------------------


def test_extra_de_tentativa_unica_ainda_faz_a_tentativa_imediata() -> None:
    """Regressão (achado do code-review): sem isto, um extra criado a partir do
    meio-dia local nunca chegava a chamar o Telegram — o despacho é sempre
    um pouco posterior à criação, e um prazo baseado no instante de criação
    era sempre "ultrapassado" já na primeira checagem."""
    pedido = replace(_pedido_pendente(), prazo=None, tentativa_unica=True)
    repositorio = RepositorioFalso(pedido)

    resultado = _worker(repositorio, CanalEspiao()).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.ENVIADO


def test_extra_de_tentativa_unica_nao_retenta_erro_transitorio() -> None:
    pedido = replace(_pedido_pendente(), prazo=None, tentativa_unica=True)
    repositorio = RepositorioFalso(pedido)
    erro = _erro_transitorio("Bot API respondeu HTTP 500")
    canal = CanalEspiao(falhar_na_parte=0, erro=erro)

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.FALHOU  # terminal: não retenta


def test_primeiro_backoff_transitorio_e_a_base_sem_dobrar() -> None:
    # Regressão (achado do code-review): sequencial=1 é a primeira tentativa, e
    # o primeiro backoff deve ser BASE_DO_BACKOFF_S — não o dobro dela.
    repositorio = RepositorioFalso(_pedido_pendente())
    erro = _erro_transitorio("Bot API respondeu HTTP 500")
    canal = CanalEspiao(falhar_na_parte=0, erro=erro)

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is not None
    assert resultado.proxima_tentativa is not None
    atraso = (resultado.proxima_tentativa - INSTANTE).total_seconds()
    base = EntregadorDePedido.BASE_DO_BACKOFF_S
    assert atraso == base


def test_conflito_ao_consumir_rele_o_ciclo_e_tenta_de_novo() -> None:
    # O pedido já está em estado terminal quando o ciclo é atualizado: um
    # conflito aqui não pode abortar o pedido, só reler e tentar de novo — outro
    # pedido pode ter avançado o mesmo item de ciclo compartilhado (ticket 09).
    repositorio = RepositorioFalso(_pedido_pendente())
    ciclos = CiclosComConflitoAoConsumir()

    _worker(repositorio, CanalEspiao(), ciclos=ciclos).executar("extra#42")

    assert ciclos.chamadas == 3
    assert ciclos.ciclo.foi_consumida("bloco-1")


# --- diária com múltiplos destinatários (ticket 25) ---------------------------

CHAT_DO_IRMAO = 111222333


def _diaria_compartilhada() -> Pedido:
    return Pedido(
        identidade="diaria#2026-09-07", origem=Origem.DIARIA, destinatarios=(CHAT, CHAT_DO_IRMAO)
    )


def test_entregador_agrega_falha_sem_finalizar_o_pedido() -> None:
    """O módulo de entrega relata o desfecho; o coordenador encerra o pedido."""
    pedido = _diaria_compartilhada().reservar("bloco-1").iniciar_envio()
    repositorio = RepositorioFalso(pedido)
    canal = CanalPorDestinatario(
        falha_para={CHAT_DO_IRMAO: ErroDoTelegram("Bot API respondeu HTTP 403")}
    )
    entregador = EntregadorDePedido(repositorio, canal, RelogioFixo(), _sem_dispersao)

    resultado = entregador.entregar(pedido, UMA_FRASE, sequencial=1)

    assert resultado.desfecho is DesfechoDaEntrega.FALHOU
    assert resultado.confirmou_algo
    assert resultado.pedido.estado is EstadoDoPedido.ENVIANDO
    assert resultado.pedido.destinatarios_com_falha == (CHAT_DO_IRMAO,)
    assert canal.enviados == [(CHAT, "parte um"), (CHAT, "parte dois")]


def test_resultado_aguardando_exige_proxima_tentativa() -> None:
    with pytest.raises(ValueError, match="próxima tentativa"):
        ResultadoDaEntrega(_diaria_compartilhada(), DesfechoDaEntrega.AGUARDANDO)


def test_diaria_compartilhada_entrega_a_mesma_frase_a_todos_os_destinatarios() -> None:
    """AC32: um único sorteio, a mesma frase para todo mundo."""
    repositorio = RepositorioFalso(_diaria_compartilhada())
    canal = CanalPorDestinatario()
    ciclos = CiclosEmMemoria()

    resultado = _worker(repositorio, canal, ciclos=ciclos).executar("diaria#2026-09-07")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.ENVIADO
    assert sorted(canal.enviados) == sorted(
        [
            (CHAT, "parte um"),
            (CHAT, "parte dois"),
            (CHAT_DO_IRMAO, "parte um"),
            (CHAT_DO_IRMAO, "parte dois"),
        ]
    )
    # AC34: uma única reserva/consumo no ciclo, não uma por destinatário.
    assert ciclos.ciclo.foi_consumida("bloco-1")
    assert ciclos.ciclo.consumidas_com_ressalva == frozenset()
    assert ciclos.ciclo.entregas_neste_ciclo == 1


def test_falha_permanente_a_um_destinatario_nao_impede_entrega_ao_outro() -> None:
    """AC33, quebrando a invariante de propósito: um erro permanente do
    Telegram para um destinatário não pode custar a entrega ao outro nem
    duplicar (ou pular) o consumo da frase no ciclo."""
    repositorio = RepositorioFalso(_diaria_compartilhada())
    canal = CanalPorDestinatario(
        falha_para={CHAT_DO_IRMAO: ErroDoTelegram("Bot API respondeu HTTP 403")}
    )
    ciclos = CiclosEmMemoria()

    resultado = _worker(repositorio, canal, ciclos=ciclos).executar("diaria#2026-09-07")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.PARCIAL
    assert (CHAT, "parte um") in canal.enviados
    assert (CHAT, "parte dois") in canal.enviados
    assert all(chat_id != CHAT_DO_IRMAO for chat_id, _ in canal.enviados)
    # A frase é consumida exatamente uma vez — nunca uma reserva órfã, nunca
    # duas vezes — mesmo com um destinatário concluído e outro falho.
    assert ciclos.ciclo.foi_consumida("bloco-1")
    assert ciclos.ciclo.reservadas == frozenset()
    assert ciclos.ciclo.consumidas_com_ressalva == frozenset({"bloco-1"})


def test_motivo_registrado_preserva_todos_os_problemas_sem_expor_destinatarios() -> None:
    """Achado do code-review: o motivo de um destinatário que falhou não pode
    desaparecer só porque outro, no mesmo instante, ficou incerto."""
    repositorio = RepositorioFalso(_diaria_compartilhada())

    class CanalComDoisDesfechos:
        def enviar_texto(self, chat_id: int, texto: str) -> int:
            if chat_id == CHAT:
                raise ErroDoTelegram("Bot API respondeu HTTP 403")
            return 0  # message_id desconhecido: vira incerto

    resultado = _worker(repositorio, CanalComDoisDesfechos()).executar("diaria#2026-09-07")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.INCERTO  # incerto tem prioridade sobre falhou
    assert "HTTP 403" in resultado.motivo_do_estado
    assert "não houve confirmação durável" in resultado.motivo_do_estado
    assert str(CHAT) not in resultado.motivo_do_estado
    assert str(CHAT_DO_IRMAO) not in resultado.motivo_do_estado


def test_reagenda_pelo_instante_mais_tardio_entre_os_que_aguardam() -> None:
    """Achado do code-review: dois destinatários com erro transitório no mesmo
    instante — o de retry_after mais curto não pode vencer o mais longo, ou a
    próxima tentativa bateria cedo demais no limite do segundo."""
    repositorio = RepositorioFalso(_diaria_compartilhada())
    canal = CanalPorDestinatario(
        falha_para={
            CHAT: _erro_transitorio("Bot API recusou: 429", retry_after_s=10),
            CHAT_DO_IRMAO: _erro_transitorio("Bot API recusou: 429", retry_after_s=300),
        }
    )

    resultado = _worker(repositorio, canal).executar("diaria#2026-09-07")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.AGUARDANDO_TENTATIVA
    assert resultado.proxima_tentativa == INSTANTE + timedelta(seconds=300)


def test_erro_transitorio_a_um_destinatario_agenda_nova_tentativa_do_pedido_inteiro() -> None:
    """Um erro transitório para um destinatário não encerra o pedido nem
    desiste do outro: o pedido inteiro aguarda nova tentativa, com a reserva
    preservada — mesmo que o outro destinatário já tenha recebido tudo nesta
    mesma passada."""
    repositorio = RepositorioFalso(_diaria_compartilhada())
    ciclos = CiclosEmMemoria()
    erro = _erro_transitorio("Bot API respondeu HTTP 500")
    canal = CanalPorDestinatario(falha_para={CHAT_DO_IRMAO: erro})

    resultado = _worker(repositorio, canal, ciclos=ciclos).executar("diaria#2026-09-07")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.AGUARDANDO_TENTATIVA
    assert resultado.frase_reservada == "bloco-1"
    assert (CHAT, "parte um") in canal.enviados
    assert (CHAT, "parte dois") in canal.enviados
    assert all(chat_id != CHAT_DO_IRMAO for chat_id, _ in canal.enviados)


class ColecaoSemSincronizacao:
    def carregar_ativa(self) -> SnapshotPersistido | None:
        return None

    def ultima_tentativa(self) -> TentativaDeSincronizacao | None:
        return None


def test_status_reconhece_entrega_completa_quando_outro_destinatario_fica_incerto() -> None:
    repositorio = RepositorioFalso(_diaria_compartilhada())

    class CanalComIncerteza:
        def enviar_texto(self, chat_id: int, texto: str) -> int:
            return 0 if chat_id == CHAT_DO_IRMAO else 901

    ciclos = CiclosEmMemoria()
    _worker(repositorio, CanalComIncerteza(), ciclos=ciclos).executar("diaria#2026-09-07")
    ciclo_antes = ciclos.carregar()
    pedido_antes = repositorio.pedido
    consulta = ConsultarStatus(repositorio, ColecaoSemSincronizacao(), RelogioFixo(), CHAT)

    confirmado = consulta.executar()
    incerto = replace(consulta, chat_id=CHAT_DO_IRMAO).executar()

    assert confirmado.situacao_da_diaria_de_hoje.estado is EstadoDoPedido.ENVIADO
    assert confirmado.ultimo_envio is not None
    assert confirmado.ultimo_envio.estado is EstadoDoPedido.ENVIADO
    assert incerto.situacao_da_diaria_de_hoje.estado is EstadoDoPedido.INCERTO
    assert ciclos.carregar() == ciclo_antes
    assert repositorio.pedido == pedido_antes


@pytest.mark.parametrize(
    ("resultado_proprio", "estado_esperado"),
    [
        ("confirmado", EstadoDoPedido.ENVIADO),
        ("incerto", EstadoDoPedido.INCERTO),
        ("falha", EstadoDoPedido.FALHOU),
        ("parcial", EstadoDoPedido.PARCIAL),
    ],
)
def test_status_proprio_independe_da_retentativa_do_outro(
    resultado_proprio: str, estado_esperado: EstadoDoPedido
) -> None:
    repositorio = RepositorioFalso(_diaria_compartilhada())

    class CanalComRetentativa:
        def enviar_texto(self, chat_id: int, texto: str) -> int:
            if chat_id == CHAT_DO_IRMAO:
                raise _erro_transitorio("Bot API respondeu HTTP 503")
            if resultado_proprio == "incerto":
                return 0
            if resultado_proprio == "falha" or (
                resultado_proprio == "parcial" and texto == "parte dois"
            ):
                raise ErroDoTelegram("Bot API respondeu HTTP 403")
            return 901

    _worker(repositorio, CanalComRetentativa()).executar("diaria#2026-09-07")
    consulta = ConsultarStatus(repositorio, ColecaoSemSincronizacao(), RelogioFixo(), CHAT)

    proprio = consulta.executar()
    outro = replace(consulta, chat_id=CHAT_DO_IRMAO).executar()

    assert proprio.situacao_da_diaria_de_hoje.estado is estado_esperado
    assert proprio.proxima_ocorrencia_diaria == datetime(2026, 9, 8, 11, tzinfo=UTC)
    assert outro.situacao_da_diaria_de_hoje.estado is EstadoDoPedido.AGUARDANDO_TENTATIVA
    assert outro.proxima_ocorrencia_diaria == datetime(2026, 9, 7, 11, tzinfo=UTC)


@pytest.mark.parametrize(
    ("falhar_na_segunda", "esperado"),
    [(False, EstadoDoPedido.FALHOU), (True, EstadoDoPedido.PARCIAL)],
)
def test_retentativa_alheia_nao_converte_falha_definitiva_em_incerteza(
    falhar_na_segunda: bool,
    esperado: EstadoDoPedido,
) -> None:
    repositorio = RepositorioFalso(_diaria_compartilhada())
    envios_proprios: list[str] = []

    class CanalComFalhasMistas:
        def enviar_texto(self, chat_id: int, texto: str) -> int:
            if chat_id == CHAT_DO_IRMAO:
                raise _erro_transitorio("Bot API respondeu HTTP 503")
            envios_proprios.append(texto)
            if not falhar_na_segunda or texto == "parte dois":
                raise ErroDoTelegram("Bot API respondeu HTTP 403")
            return 901

    class RelogioDaRetentativa:
        def agora(self) -> datetime:
            return INSTANTE + timedelta(minutes=2)

    worker = _worker(repositorio, CanalComFalhasMistas())
    worker.executar("diaria#2026-09-07")
    consulta = ConsultarStatus(repositorio, ColecaoSemSincronizacao(), RelogioFixo(), CHAT)
    assert consulta.executar().situacao_da_diaria_de_hoje.estado is esperado
    envios_antes = list(envios_proprios)

    replace(worker, relogio=RelogioDaRetentativa()).executar("diaria#2026-09-07")

    situacao = consulta.executar().situacao_da_diaria_de_hoje
    assert situacao.estado is esperado
    assert situacao.tem_partes_incertas is False
    assert envios_proprios == envios_antes


def test_no_instante_limite_nao_inicia_nenhuma_parte() -> None:
    pedido = replace(_pedido_pendente(), prazo=INSTANTE)
    repositorio, canal = RepositorioFalso(pedido), CanalEspiao()

    resultado = _worker(repositorio, canal).executar(pedido.identidade)

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.EXPIRADO
    assert canal.enviados == []


@pytest.mark.parametrize("retomada", [False, True])
def test_incerteza_mantem_frase_consumida_com_ressalva_sem_afirmar_sucesso(
    retomada: bool,
) -> None:
    pedido = _pedido_pendente()
    repositorio = RepositorioFalso(pedido)
    ciclos = CiclosEmMemoria()

    class CanalComAmbiguidade:
        def enviar_texto(self, chat_id: int, texto: str) -> int:
            return 0

    canal: CanalComAmbiguidade | CanalEspiao = CanalComAmbiguidade()
    if retomada:
        repositorio.pedido = replace(
            pedido.reservar("bloco-1").iniciar_envio(),
            partes_reservadas=UMA_FRASE.partes,
            total_de_partes=len(UMA_FRASE.partes),
        )
        repositorio.incertas.append({"destinatario": CHAT, "indice": 0, "motivo": "incerta"})
        ciclos.ciclo = ciclos.ciclo.reservar("bloco-1")
        canal = CanalEspiao()

    resultado = _worker(repositorio, canal, ciclos=ciclos).executar(pedido.identidade)

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.INCERTO
    assert ciclos.ciclo.consumidas_com_ressalva == frozenset({"bloco-1"})
    assert ciclos.ciclo.reservadas == frozenset()
    if isinstance(canal, CanalEspiao):
        assert canal.enviados == ["parte dois"]


@pytest.mark.parametrize("motivo_do_encerramento", ["falha_permanente", "prazo_esgotado"])
def test_encerramento_da_retomada_preserva_incerteza_e_consumo_com_ressalva(
    motivo_do_encerramento: str,
) -> None:
    pedido = _diaria_compartilhada().reservar("bloco-1").iniciar_envio()
    if motivo_do_encerramento == "prazo_esgotado":
        pedido = replace(pedido, prazo=INSTANTE)
    repositorio = RepositorioFalso(pedido)
    repositorio.incertas.append({"destinatario": CHAT, "indice": 0, "motivo": "incerta"})
    ciclos = CiclosEmMemoria()
    ciclos.ciclo = ciclos.ciclo.reservar("bloco-1")
    envios: list[tuple[int, str]] = []

    class CanalComFalhaPermanente:
        def enviar_texto(self, chat_id: int, texto: str) -> int:
            envios.append((chat_id, texto))
            raise ErroDoTelegram("Bot API respondeu HTTP 403")

    resultado = _worker(repositorio, CanalComFalhaPermanente(), ciclos=ciclos).executar(
        pedido.identidade
    )

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.INCERTO
    assert ciclos.ciclo.consumidas_com_ressalva == frozenset({"bloco-1"})
    assert ciclos.ciclo.reservadas == frozenset()
    consulta = ConsultarStatus(repositorio, ColecaoSemSincronizacao(), RelogioFixo(), CHAT)
    assert consulta.executar().situacao_da_diaria_de_hoje.estado is EstadoDoPedido.INCERTO
    assert (CHAT, "parte um") not in envios
    if motivo_do_encerramento == "prazo_esgotado":
        assert envios == []
