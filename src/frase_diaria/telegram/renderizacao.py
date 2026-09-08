"""Renderiza conteúdo preservado no HTML aceito pela Bot API."""

from dataclasses import dataclass
from html import escape

from frase_diaria.dominio.colecao import FrasePreservada
from frase_diaria.dominio.conteudo import Trecho
from frase_diaria.dominio.frase import Frase

LIMITE_TEXTO_TELEGRAM = 4096


@dataclass(frozen=True)
class RenderizadorTelegram:
    """Converte uma frase rica em partes HTML válidas e limitadas."""

    limite_de_texto: int = LIMITE_TEXTO_TELEGRAM

    def __post_init__(self) -> None:
        if self.limite_de_texto < 1:
            raise ValueError("limite de texto precisa ser positivo")

    def renderizar(self, preservada: FrasePreservada) -> Frase | None:
        segmentos = _segmentos_da_frase(preservada)
        if not segmentos:
            return None
        partes = _dividir_segmentos(segmentos, self.limite_de_texto)
        return Frase(identidade=preservada.identidade, partes=tuple(partes))


@dataclass(frozen=True)
class _Segmento:
    texto: str
    prefixo: str = ""
    sufixo: str = ""


def _segmentos_da_frase(preservada: FrasePreservada) -> tuple[_Segmento, ...]:
    segmentos: list[_Segmento] = []
    blocos_com_texto = [
        bloco for bloco in preservada.blocos if any(trecho.texto for trecho in bloco.trechos)
    ]
    for indice, bloco in enumerate(blocos_com_texto):
        if indice:
            segmentos.append(_Segmento("\n"))
        segmentos.extend(_segmento_do_trecho(trecho) for trecho in bloco.trechos if trecho.texto)
    return tuple(segmentos)


def _segmento_do_trecho(trecho: Trecho) -> _Segmento:
    tags: list[tuple[str, str]] = []
    if trecho.negrito or _tem_destaque_sem_equivalente(trecho):
        tags.append(("<b>", "</b>"))
    if trecho.italico:
        tags.append(("<i>", "</i>"))
    if trecho.tachado:
        tags.append(("<s>", "</s>"))
    if trecho.sublinhado:
        tags.append(("<u>", "</u>"))
    if trecho.codigo:
        tags.append(("<code>", "</code>"))
    if trecho.link:
        tags.append((f'<a href="{escape(trecho.link, quote=True)}">', "</a>"))
    return _Segmento(
        texto=trecho.texto,
        prefixo="".join(abertura for abertura, _ in tags),
        sufixo="".join(fechamento for _, fechamento in reversed(tags)),
    )


def _tem_destaque_sem_equivalente(trecho: Trecho) -> bool:
    return trecho.cor != "default" or trecho.fundo != "default"


def _dividir_segmentos(segmentos: tuple[_Segmento, ...], limite: int) -> list[str]:
    partes: list[str] = []
    atual: list[str] = []
    tamanho_atual = 0
    for segmento in segmentos:
        inicio = 0
        while inicio < len(segmento.texto):
            disponivel = limite - tamanho_atual
            if disponivel == 0:
                partes.append("".join(atual))
                atual, tamanho_atual = [], 0
                disponivel = limite
            fim = min(inicio + disponivel, len(segmento.texto))
            trecho = segmento.texto[inicio:fim]
            atual.append(segmento.prefixo + escape(trecho) + segmento.sufixo)
            tamanho_atual += len(trecho)
            inicio = fim
    if atual:
        partes.append("".join(atual))
    return partes
