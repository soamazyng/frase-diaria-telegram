"""O worker: transforma um pedido persistido em mensagens entregues.

Duas regras governam: o worker lê o pedido da persistência (nunca do corpo de uma
requisição), e uma parte só conta como entregue quando o Telegram confirmou **e**
a confirmação foi persistida.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from frase_diaria.aplicacao.portas import ConflitoDeConcorrencia
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

    def registrar_intencao_parte(self, pedido: str, indice: int, texto: str, instante: Any) -> None:
        self.intencoes.append({"indice": indice, "texto": texto})

    def confirmar_parte(
        self,
        pedido: str,
        indice: int,
        texto: str,
        message_id: int,
        instante: Any,
        sequencial: int | None = None,
    ) -> None:
        self._verificar_lease(sequencial)
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


def _pedido_pendente() -> Pedido:
    return Pedido(identidade="extra#42", origem=Origem.EXTRA, chat_id=CHAT)


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
    worker = ProcessarPedido(
        repositorio=repositorio,
        fonte=FonteFixa(),
        canal=CanalEspiao(),
        sorteio=SorteioPrevisivel(),
        relogio=RelogioFixo(),
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
    worker = ProcessarPedido(
        repositorio=repositorio,
        fonte=FonteFixa((outra,)),
        canal=CanalEspiao(),
        sorteio=SorteioPrevisivel(),
        relogio=RelogioFixo(),
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
    erro = ErroDoTelegram("Bot API respondeu HTTP 500", codigo_http=500, transitorio=True)
    canal = CanalEspiao(falhar_na_parte=0, erro=erro)

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.AGUARDANDO_TENTATIVA
    assert resultado.frase_reservada == "bloco-1"  # a reserva não é liberada
    assert resultado.proxima_tentativa is not None
    assert resultado.proxima_tentativa > INSTANTE


def test_erro_transitorio_respeita_o_retry_after_do_telegram() -> None:
    repositorio = RepositorioFalso(_pedido_pendente())
    erro = ErroDoTelegram("Bot API recusou: 429", transitorio=True, retry_after_s=7)
    canal = CanalEspiao(falhar_na_parte=0, erro=erro)

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is not None
    assert resultado.proxima_tentativa == INSTANTE + timedelta(seconds=7)


def test_erro_transitorio_apos_o_prazo_encerra_em_vez_de_retentar() -> None:
    pedido = replace(_pedido_pendente(), prazo=INSTANTE - timedelta(minutes=1))
    repositorio = RepositorioFalso(pedido)
    erro = ErroDoTelegram("Bot API respondeu HTTP 500", transitorio=True)
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
    repositorio.partes.append({"indice": 0, "texto": "parte um", "message_id": 901})
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
    worker = ProcessarPedido(
        repositorio=repositorio,
        fonte=FonteFixa(),
        canal=canal,
        sorteio=SorteioPrevisivel(),
        relogio=RelogioQueAvancaAposUmEnvio(canal),
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
    erro = ErroDoTelegram("Bot API respondeu HTTP 500", transitorio=True)
    canal = CanalEspiao(falhar_na_parte=0, erro=erro)

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is not None
    assert resultado.estado is EstadoDoPedido.FALHOU  # terminal: não retenta


def test_primeiro_backoff_transitorio_e_a_base_sem_dobrar() -> None:
    # Regressão (achado do code-review): sequencial=1 é a primeira tentativa, e
    # o primeiro backoff deve ser BASE_DO_BACKOFF_S — não o dobro dela.
    repositorio = RepositorioFalso(_pedido_pendente())
    erro = ErroDoTelegram("Bot API respondeu HTTP 500", transitorio=True)
    canal = CanalEspiao(falhar_na_parte=0, erro=erro)

    resultado = _worker(repositorio, canal).executar("extra#42")

    assert resultado is not None
    assert resultado.proxima_tentativa is not None
    atraso = (resultado.proxima_tentativa - INSTANTE).total_seconds()
    base = ProcessarPedido.BASE_DO_BACKOFF_S
    assert base <= atraso <= base * 1.1  # base + até 10% de dispersão


def test_conflito_ao_consumir_rele_o_ciclo_e_tenta_de_novo() -> None:
    # O pedido já está em estado terminal quando o ciclo é atualizado: um
    # conflito aqui não pode abortar o pedido, só reler e tentar de novo — outro
    # pedido pode ter avançado o mesmo item de ciclo compartilhado (ticket 09).
    repositorio = RepositorioFalso(_pedido_pendente())
    ciclos = CiclosComConflitoAoConsumir()

    _worker(repositorio, CanalEspiao(), ciclos=ciclos).executar("extra#42")

    assert ciclos.chamadas == 3
    assert ciclos.ciclo.foi_consumida("bloco-1")
