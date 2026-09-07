"""O worker: transforma um pedido persistido em mensagens entregues.

Duas regras governam: o worker lê o pedido da persistência (nunca do corpo de uma
requisição), e uma parte só conta como entregue quando o Telegram confirmou **e**
a confirmação foi persistida.
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from frase_diaria.aplicacao.processar_pedido import ProcessarPedido, ReservaPendente
from frase_diaria.dominio.ciclo import Ciclo
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
        self.intencoes: list[dict[str, Any]] = []
        self.incertas: list[dict[str, Any]] = []

    def obter(self, identidade: str) -> Pedido | None:
        return self.pedido

    def salvar(self, pedido: Pedido) -> None:
        self.pedido = pedido
        self.salvos.append(pedido)

    def registrar_intencao_parte(self, pedido: str, indice: int, texto: str, instante: Any) -> None:
        self.intencoes.append({"indice": indice, "texto": texto})

    def confirmar_parte(
        self, pedido: str, indice: int, texto: str, message_id: int, instante: Any
    ) -> None:
        self.partes.append({"indice": indice, "texto": texto, "message_id": message_id})

    def marcar_parte_incerta(self, pedido: str, indice: int, motivo: str, instante: Any) -> None:
        self.incertas.append({"indice": indice, "motivo": motivo})

    def indices_confirmados(self, pedido: str) -> set[int]:
        return {p["indice"] for p in self.partes}

    def indices_incertos(self, pedido: str) -> set[int]:
        return {p["indice"] for p in self.incertas}

    def indices_intencoes(self, pedido: str) -> set[int]:
        return {p["indice"] for p in self.intencoes}

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


class ReservaEmMemoria:
    """Faz o papel da transação: grava ciclo e pedido juntos."""

    def __init__(self, ciclos: Any, repositorio: Any) -> None:
        self.ciclos = ciclos
        self.repositorio = repositorio

    def efetivar(self, pedido: Any, ciclo: Any) -> None:
        self.ciclos.salvar(ciclo)
        self.repositorio.salvar(pedido)


class CiclosEmMemoria:
    def __init__(self, ciclo: Ciclo | None = None) -> None:
        self.ciclo = ciclo if ciclo is not None else Ciclo.primeiro()

    def carregar(self) -> Ciclo:
        return self.ciclo

    def salvar(self, ciclo: Ciclo) -> None:
        self.ciclo = ciclo


def _worker(
    repositorio: Any,
    canal: Any,
    fonte: Any | None = None,
    ciclos: Any | None = None,
) -> ProcessarPedido:
    ciclos = ciclos if ciclos is not None else CiclosEmMemoria()
    return ProcessarPedido(
        repositorio=repositorio,
        fonte=fonte if fonte is not None else FonteFixa(),
        canal=canal,
        sorteio=SorteioPrevisivel(),
        relogio=RelogioFixo(),
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
    assert repositorio.partes[0] == {"indice": 0, "texto": "parte um", "message_id": 901}
    assert repositorio.partes[1] == {"indice": 1, "texto": "parte dois", "message_id": 902}


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
            "indice": 0,
            "motivo": "Telegram pode ter aceitado a parte, mas não houve confirmação durável",
        }
    ]
    assert repositorio.partes == []


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


# --- retomada ----------------------------------------------------------------


def test_retomada_envia_apenas_as_partes_que_faltam() -> None:
    em_andamento = _pedido_pendente().reservar("bloco-1")
    repositorio = RepositorioFalso(em_andamento)
    repositorio.partes.append({"indice": 0, "texto": "parte um", "message_id": 901})
    canal = CanalEspiao()
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-1"))

    _worker(repositorio, canal, ciclos=ciclos).executar("extra#42")

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
    em_andamento = _pedido_pendente().reservar("bloco-sumida").iniciar_envio()
    repositorio = RepositorioFalso(em_andamento)
    repositorio.partes.append({"indice": 0, "texto": "já foi", "message_id": 901})
    ciclos = CiclosEmMemoria(Ciclo.primeiro().reservar("bloco-sumida"))

    resultado = _worker(repositorio, CanalEspiao(), fonte=FonteFixa(()), ciclos=ciclos).executar(
        "extra#42"
    )

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.PARCIAL
    assert resultado.frase_reservada == "bloco-sumida"


# --- ciclo atravessando as camadas -------------------------------------------

COLECAO = tuple(Frase(identidade=f"f{n}", partes=(f"frase {n}",)) for n in range(1, 4))


class SorteioDoUltimo:
    def escolher(self, candidatos: Any) -> Any:
        return candidatos[-1]


def _entregar_uma(ciclos: Any, update_id: int, sorteio: Any = None) -> str:
    """Roda um pedido inteiro e devolve o texto entregue."""
    repositorio = RepositorioFalso(
        Pedido(identidade=f"extra#{update_id}", origem=Origem.EXTRA, chat_id=CHAT)
    )
    canal = CanalEspiao()
    worker = ProcessarPedido(
        repositorio=repositorio,
        fonte=FonteFixa(COLECAO),
        canal=canal,
        sorteio=sorteio if sorteio is not None else SorteioPrevisivel(),
        relogio=RelogioFixo(),
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
        def salvar(self, pedido: Any) -> None:
            ordem.append("pedido")
            super().salvar(pedido)

    class CiclosQueAnotam(CiclosEmMemoria):
        def salvar(self, ciclo: Any) -> None:
            ordem.append("ciclo")
            super().salvar(ciclo)

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
