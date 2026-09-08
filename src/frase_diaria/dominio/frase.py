from dataclasses import dataclass


@dataclass(frozen=True)
class Frase:
    """Um item da coleção, pronto para entrega.

    `identidade` é o id do bloco raiz na fonte, nunca o texto: mover ou editar um
    bloco preserva a identidade, e igualdade de texto jamais serve como critério
    de deduplicação.

    A frase é uma **entrega lógica**: pode ocupar várias mensagens no Telegram e
    ainda assim conta como uma única frase consumida do ciclo.
    """

    identidade: str
    partes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.identidade.strip():
            raise ValueError("frase precisa de identidade")
        if not self.partes:
            raise ValueError("frase precisa de ao menos uma parte")
        if any(not parte.strip() for parte in self.partes):
            raise ValueError("frase não pode ter parte vazia")

    @property
    def quantidade_de_partes(self) -> int:
        return len(self.partes)
