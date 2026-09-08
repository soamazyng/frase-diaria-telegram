from dataclasses import dataclass


@dataclass(frozen=True)
class Trecho:
    """Um segmento de rich text preservado literalmente.

    Autoria misturada ao texto nunca é separada por heurística: o texto de
    `texto` é exatamente o que a fonte trouxe (spec, 4.2).
    """

    texto: str
    negrito: bool = False
    italico: bool = False
    tachado: bool = False
    sublinhado: bool = False
    codigo: bool = False
    link: str | None = None
    cor: str = "default"
    fundo: str = "default"


@dataclass(frozen=True)
class Bloco:
    """Um bloco de conteúdo, na posição em que aparece na página de origem.

    `tipo` é o tipo bruto do bloco na fonte (`paragraph`, `quote`, `image`, ...).
    Decidir como cada tipo vira mensagem do Telegram pertence à renderização
    (ticket 12); aqui só se preserva o que veio, na ordem em que veio.
    """

    tipo: str
    trechos: tuple[Trecho, ...] = ()
