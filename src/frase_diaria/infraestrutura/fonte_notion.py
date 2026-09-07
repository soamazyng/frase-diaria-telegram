import logging
from dataclasses import dataclass
from typing import Protocol

from frase_diaria.aplicacao.sincronizar_colecao import ResultadoDaSincronizacao
from frase_diaria.dominio.colecao import FrasePreservada
from frase_diaria.dominio.frase import Frase

_log = logging.getLogger(__name__)


class Sincronizador(Protocol):
    def executar(self) -> ResultadoDaSincronizacao: ...


@dataclass(frozen=True)
class FonteDeFrasesNotion:
    """Adapta a sincronização (com cache) à porta `FonteDeFrases` do worker.

    A conversão de conteúdo preservado para texto plano é um placeholder até o
    ticket 12 (renderização rica e divisão de mensagens): concatena o texto
    literal dos trechos, sem formatação nem divisão inteligente entre partes.
    """

    sincronizar: Sincronizador

    def listar(self) -> tuple[Frase, ...]:
        resultado = self.sincronizar.executar()
        frases = []
        for item in resultado.colecao.itens:
            frase = _para_frase(item)
            if frase is None:
                # Sem nenhum trecho em nenhum bloco (ex.: um bloco de imagem
                # sozinho — cache de mídia é do ticket 13). Ignorar só esta
                # frase é o que impede uma exceção aqui de derrubar a entrega
                # de todas as outras.
                _log.warning("frase sem conteúdo textual ignorada")
                continue
            frases.append(frase)
        return tuple(frases)


def _para_frase(preservada: FrasePreservada) -> Frase | None:
    linhas = [
        "".join(t.texto for t in bloco.trechos) for bloco in preservada.blocos if bloco.trechos
    ]
    if not linhas:
        return None
    return Frase(identidade=preservada.identidade, partes=("\n".join(linhas),))
