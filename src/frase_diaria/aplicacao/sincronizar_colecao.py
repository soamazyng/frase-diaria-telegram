import logging
from dataclasses import dataclass
from datetime import datetime

from frase_diaria.aplicacao.portas import FonteDaColecao, Relogio, RepositorioDeColecao
from frase_diaria.dominio.colecao import ColecaoValida, SincronizacaoIncompleta

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResultadoDaSincronizacao:
    """O que a sincronização decidiu: publicar o que leu, ou usar o cache."""

    colecao: ColecaoValida
    usou_cache: bool
    instante_do_snapshot: datetime
    erro_da_sincronizacao: str | None = None


@dataclass(frozen=True)
class SincronizarColecao:
    """Lê a fonte e decide entre publicar um snapshot novo ou usar o cache.

    Notion indisponível usa a última coleção válida, indicando uso de cache,
    a data desse snapshot e o erro da sincronização; sem cache disponível, a
    falha propaga para quem chama (AC09). Uma leitura bem-sucedida — mesmo
    legitimamente vazia — sempre substitui o snapshot persistido: nunca
    ressuscita frases excluídas por continuar servindo a versão anterior.
    """

    leitor: FonteDaColecao
    repositorio: RepositorioDeColecao
    pagina_id: str
    relogio: Relogio

    def executar(self) -> ResultadoDaSincronizacao:
        agora = self.relogio.agora()
        try:
            colecao = self.leitor.ler(self.pagina_id)
        except SincronizacaoIncompleta as erro:
            cache = self.repositorio.carregar_ativa()
            if cache is None:
                raise
            _log.warning("Notion indisponível; usando snapshot de %s", cache.instante)
            return ResultadoDaSincronizacao(
                colecao=cache.colecao,
                usou_cache=True,
                instante_do_snapshot=cache.instante,
                erro_da_sincronizacao=str(erro),
            )
        self.repositorio.substituir(colecao, agora)
        return ResultadoDaSincronizacao(
            colecao=colecao, usou_cache=False, instante_do_snapshot=agora
        )
