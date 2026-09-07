"""O worker: transforma um pedido persistido em mensagens entregues.

Duas regras governam: o worker lê o pedido da persistência (nunca do corpo de uma
requisição), e uma parte só conta como entregue quando o Telegram confirmou **e**
a confirmação foi persistida.
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from frase_diaria.aplicacao.processar_pedido import ProcessarPedido
from frase_diaria.dominio.frase import Frase
from frase_diaria.dominio.pedido import EstadoDoPedido, Origem, Pedido
from frase_diaria.telegram.canal import ErroDoTelegram

CHAT = 672024065
UMA_FRASE = Frase(identidade="bloco-1", partes=("parte um", "parte dois"))
INSTANTE = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


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

    def obter(self, identidade: str) -> Pedido | None:
        return self.pedido

    def salvar(self, pedido: Pedido) -> None:
        self.pedido = pedido
        self.salvos.append(pedido)

    def confirmar_parte(
        self, pedido: str, indice: int, texto: str, message_id: int, instante: Any
    ) -> None:
        self.partes.append({"indice": indice, "texto": texto, "message_id": message_id})

    def indices_confirmados(self, pedido: str) -> set[int]:
        return {p["indice"] for p in self.partes}

    def registrar_tentativa(
        self, pedido: str, resultado: str, erro: str | None, instante: Any
    ) -> None:
        self.tentativas.append({"resultado": resultado, "erro": erro})


class CanalEspiao:
    def __init__(self, falhar_na_parte: int | None = None) -> None:
        self.enviados: list[str] = []
        self.falhar_na_parte = falhar_na_parte

    def enviar_texto(self, chat_id: int, texto: str) -> int:
        if self.falhar_na_parte is not None and len(self.enviados) == self.falhar_na_parte:
            raise ErroDoTelegram("Bot API respondeu HTTP 500")
        self.enviados.append(texto)
        return 900 + len(self.enviados)


def _pedido_pendente() -> Pedido:
    return Pedido(identidade="extra#42", origem=Origem.EXTRA, chat_id=CHAT)


def _worker(repositorio: Any, canal: Any, fonte: Any | None = None) -> ProcessarPedido:
    return ProcessarPedido(
        repositorio=repositorio,
        fonte=fonte if fonte is not None else FonteFixa(),
        canal=canal,
        sorteio=SorteioPrevisivel(),
        relogio=RelogioFixo(),
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
    assert repositorio.partes[0] == {"indice": 0, "texto": "parte um", "message_id": 901}
    assert repositorio.partes[1] == {"indice": 1, "texto": "parte dois", "message_id": 902}


def test_registra_a_tentativa_bem_sucedida() -> None:
    repositorio, canal = RepositorioFalso(_pedido_pendente()), CanalEspiao()

    _worker(repositorio, canal).executar("extra#42")

    assert repositorio.tentativas[-1]["resultado"] == "enviado"
    assert repositorio.tentativas[-1]["erro"] is None


# --- o worker lê da persistência ---------------------------------------------


def test_pedido_inexistente_nao_envia_nada() -> None:
    repositorio, canal = RepositorioFalso(None), CanalEspiao()

    resultado = _worker(repositorio, canal).executar("extra#999")

    assert resultado is None
    assert canal.enviados == []


def test_pedido_ja_concluido_nao_reenvia() -> None:
    concluido = _pedido_pendente().reservar("bloco-1").concluir()
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


# --- retomada ----------------------------------------------------------------


def test_retomada_envia_apenas_as_partes_que_faltam() -> None:
    em_andamento = _pedido_pendente().reservar("bloco-1")
    repositorio = RepositorioFalso(em_andamento)
    repositorio.partes.append({"indice": 0, "texto": "parte um", "message_id": 901})
    canal = CanalEspiao()

    _worker(repositorio, canal).executar("extra#42")

    assert canal.enviados == ["parte dois"]


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

    _worker(repositorio, canal, fonte=FonteFixa((UMA_FRASE, outra))).executar("extra#42")

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

    with pytest.raises(RuntimeError, match="boto3 estourou"):
        _worker(repositorio, CanalQueQuebra()).executar("extra#42")

    assert repositorio.tentativas[-1]["resultado"] == "erro"
    assert "boto3 estourou" in (repositorio.tentativas[-1]["erro"] or "")


def test_erro_inesperado_nao_deixa_o_pedido_em_estado_terminal() -> None:
    repositorio = RepositorioFalso(_pedido_pendente())

    with pytest.raises(RuntimeError):
        _worker(repositorio, CanalQueQuebra()).executar("extra#42")

    assert repositorio.pedido is not None
    assert not repositorio.pedido.estado.terminal


# --- frase que sumiu da fonte ------------------------------------------------


def test_frase_reservada_sumiu_depois_de_entregar_parte_mantem_a_reserva() -> None:
    """Exclusão na fonte não pode apagar o rastro de uma entrega parcial.

    Liberar a reserva aqui violaria a invariante de que entrega parcial mantém a
    frase consumida — e registraria "sem frases" para um pedido que enviou algo.
    """
    em_andamento = _pedido_pendente().reservar("bloco-sumida")
    repositorio = RepositorioFalso(em_andamento)
    repositorio.partes.append({"indice": 0, "texto": "já foi", "message_id": 901})

    resultado = _worker(repositorio, CanalEspiao(), fonte=FonteFixa(())).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.PARCIAL
    assert resultado.frase_reservada == "bloco-sumida"
