import logging
from dataclasses import dataclass, field
from typing import Protocol

from frase_diaria.aplicacao.sincronizar_colecao import ResultadoDaSincronizacao
from frase_diaria.dominio.frase import Frase
from frase_diaria.telegram.renderizacao import RenderizadorTelegram

_log = logging.getLogger(__name__)


class Sincronizador(Protocol):
    def executar(self) -> ResultadoDaSincronizacao: ...


@dataclass(frozen=True)
class FonteDeFrasesNotion:
    """Adapta a sincronização (com cache) à porta `FonteDeFrases` do worker.

    A fonte permanece responsável apenas por adaptar o snapshot à porta do
    worker; a renderização rica e a divisão respeitando o limite do Telegram
    ficam encapsuladas em `RenderizadorTelegram`.
    """

    sincronizar: Sincronizador
    renderizador: RenderizadorTelegram = field(default_factory=RenderizadorTelegram)

    def listar(self) -> tuple[Frase, ...]:
        resultado = self.sincronizar.executar()
        frases = []
        for item in resultado.colecao.itens:
            frase = self.renderizador.renderizar(item)
            if frase is None:
                # Sem nenhum trecho em nenhum bloco (ex.: um bloco de imagem
                # sozinho — cache de mídia é do ticket 13). Ignorar só esta
                # frase é o que impede uma exceção aqui de derrubar a entrega
                # de todas as outras.
                _log.warning("frase sem conteúdo textual ignorada")
                continue
            frases.append(frase)
        return tuple(frases)
