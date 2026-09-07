"""Coleção de exemplo, embutida no código.

Existe para fechar o caminho comando → pedido → worker → mensagem antes de o
Notion entrar (ticket 10), quando este módulo sai de cena.

A autoria vem **junto do texto**, literalmente, como estará no Notion: separá-la
em campo próprio exigiria heurística, e heurística inventa atribuição.
"""

from frase_diaria.dominio.frase import Frase

FRASES: tuple[Frase, ...] = (
    Frase(
        identidade="fixture-01",
        partes=("Feito é melhor que perfeito.\n— Sheryl Sandberg",),
    ),
    Frase(
        identidade="fixture-02",
        partes=("A pergunta não é o que você olha, mas o que você vê.\n— Henry David Thoreau",),
    ),
    Frase(
        identidade="fixture-03",
        partes=("Cuidado com a esterilidade de uma vida ocupada.\n— Sócrates",),
    ),
    Frase(
        identidade="fixture-04",
        partes=("Não é que tenhamos pouco tempo, é que perdemos muito dele.\n— Sêneca",),
    ),
    # Frase de duas partes: exercita a entrega lógica ocupando mais de uma
    # mensagem, que é como frases longas do Notion vão chegar.
    Frase(
        identidade="fixture-05",
        partes=(
            "Disciplina é escolher entre o que você quer agora " "e o que você quer mais.",
            "— atribuída a Abraham Lincoln",
        ),
    ),
)


class ColecaoFixture:
    """Adaptador da porta FonteDeFrases sobre a coleção embutida."""

    def listar(self) -> tuple[Frase, ...]:
        return FRASES
