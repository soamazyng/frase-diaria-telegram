import random
from collections.abc import Sequence


class SorteioAleatorio:
    """Sorteio de produção. Recebe o gerador para permitir semente fixa em testes."""

    def __init__(self, aleatorio: random.Random | None = None) -> None:
        self._aleatorio = aleatorio if aleatorio is not None else random.SystemRandom()

    def escolher[T](self, candidatos: Sequence[T]) -> T:
        return self._aleatorio.choice(candidatos)
