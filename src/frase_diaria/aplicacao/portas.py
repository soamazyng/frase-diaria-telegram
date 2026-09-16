from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from frase_diaria.dominio.colecao import ColecaoValida, SnapshotPersistido, TentativaDeSincronizacao
from frase_diaria.dominio.pedido import Pedido


class CriadorDePedidos(Protocol):
    def criar_se_ausente(self, pedido: Pedido, instante: datetime) -> bool: ...


class Relogio(Protocol):
    """Fonte do tempo. Substituível nos testes para exercitar a janela de envio."""

    def agora(self) -> datetime:
        """Instante atual, sempre com fuso declarado (UTC em produção)."""
        ...


class ConflitoDeConcorrencia(RuntimeError):
    """Uma escrita condicional perdeu a corrida: outro executor já avançou o estado.

    Cobre tanto a versão do ciclo quanto o lease de um pedido — nos dois casos, a
    escrita foi recusada porque o que estava em memória já não é o que está
    persistido, e sobrescrever corromperia o estado (spec, 4.9).
    """


ID_DE_MENSAGEM_DESCONHECIDO = 0


@dataclass(frozen=True)
class ChaveDeParte:
    pedido: str
    destinatario: int
    indice: int


@dataclass(frozen=True)
class TentativaDeParte:
    instante: datetime
    sequencial: int | None


@dataclass(frozen=True)
class IntencaoDeParte:
    chave: ChaveDeParte
    texto: str
    tentativa: TentativaDeParte


@dataclass(frozen=True)
class ConteudoConfirmado:
    texto: str
    message_id: int


@dataclass(frozen=True)
class ConfirmacaoDeParte:
    chave: ChaveDeParte
    conteudo: ConteudoConfirmado
    tentativa: TentativaDeParte


@dataclass(frozen=True)
class IncertezaDeParte:
    chave: ChaveDeParte
    motivo: str
    tentativa: TentativaDeParte


@dataclass(frozen=True)
class ClassificacaoDoErroDeEnvio:
    codigo_http: int | None = None
    retry_after_s: float | None = None
    transitorio: bool = False
    resultado_ambiguo: bool = False


class ErroDeEnvio(RuntimeError):
    """Falha sanitizada de um canal externo.

    ``resultado_ambiguo`` separa uma rejeição confirmada de uma conexão que
    caiu sem resposta. Só a primeira permite apagar a intenção e retentar sem
    risco de duplicar uma mensagem que o provedor pode ter aceitado.
    """

    def __init__(
        self,
        mensagem: str,
        classificacao: ClassificacaoDoErroDeEnvio | None = None,
    ) -> None:
        super().__init__(mensagem)
        detalhes = classificacao or ClassificacaoDoErroDeEnvio()
        self.codigo_http = detalhes.codigo_http
        self.retry_after_s = detalhes.retry_after_s
        self.transitorio = detalhes.transitorio
        self.resultado_ambiguo = detalhes.resultado_ambiguo


class FonteDaColecao(Protocol):
    """Lê a coleção completa e validada da fonte externa (Notion)."""

    def ler(self, pagina_id: str) -> ColecaoValida:
        """Levanta `SincronizacaoIncompleta` numa leitura parcial ou com erro."""
        ...


class RepositorioDeColecao(Protocol):
    """O snapshot ativo da coleção — o que sobra quando a fonte está fora do ar."""

    def carregar_ativa(self) -> SnapshotPersistido | None: ...
    def substituir(self, colecao: ColecaoValida, instante: datetime) -> None:
        """Publica um novo snapshot ativo, inclusive um legitimamente vazio."""
        ...

    def registrar_tentativa(self, tentativa: TentativaDeSincronizacao) -> None:
        """Registra o resultado da tentativa mais recente, sucesso ou falha.

        `/status` lê isto para relatar "última tentativa" e "falha ativa" sem
        precisar disparar uma sincronização nova (spec, 4.7).
        """
        ...

    def ultima_tentativa(self) -> TentativaDeSincronizacao | None: ...
