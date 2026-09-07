from dataclasses import dataclass
from typing import Any, ClassVar

from frase_diaria.dominio.ciclo import Ciclo


@dataclass(frozen=True)
class RepositorioDeCiclosDynamo:
    """O ciclo corrente, em um único item.

    Cabe em um item porque o ciclo é limitado pela coleção — algumas dezenas de
    identidades — e zera a cada reinício. Não é o histórico: esse vive nas partes
    e tentativas de cada pedido, que ficam em itens próprios.

    A proteção contra dois executores concorrentes é do ticket 09: aqui a
    gravação ainda sobrescreve o item inteiro.
    """

    tabela: Any

    CHAVE: ClassVar[dict[str, str]] = {"pk": "ciclo", "sk": "atual"}

    def carregar(self) -> Ciclo:
        item = self.tabela.get_item(Key=self.CHAVE, ConsistentRead=True).get("Item")
        if item is None:
            return Ciclo.primeiro()
        return Ciclo(
            numero=int(item["numero"]),
            consumidas=frozenset(item.get("consumidas") or ()),
            reservadas=frozenset(item.get("reservadas") or ()),
            consumidas_com_ressalva=frozenset(item.get("com_ressalva") or ()),
            ultima_entregue=item.get("ultima_entregue") or None,
            entregas_neste_ciclo=int(item.get("entregas", 0)),
        )

    @classmethod
    def item_de(cls, ciclo: Ciclo) -> dict[str, Any]:
        """Serializa o ciclo. Compartilhado com a gravação transacional."""
        item: dict[str, Any] = {
            **cls.CHAVE,
            "numero": ciclo.numero,
            "ultima_entregue": ciclo.ultima_entregue or "",
            "entregas": ciclo.entregas_neste_ciclo,
        }
        # O DynamoDB recusa conjuntos vazios: o atributo simplesmente não vai.
        for nome, valores in (
            ("consumidas", ciclo.consumidas),
            ("reservadas", ciclo.reservadas),
            ("com_ressalva", ciclo.consumidas_com_ressalva),
        ):
            if valores:
                item[nome] = set(valores)
        return item

    def salvar(self, ciclo: Ciclo) -> None:
        self.tabela.put_item(Item=self.item_de(ciclo))
