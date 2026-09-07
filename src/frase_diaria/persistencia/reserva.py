from dataclasses import dataclass
from typing import Any

from frase_diaria.dominio.ciclo import Ciclo
from frase_diaria.dominio.pedido import Pedido
from frase_diaria.persistencia.ciclos import RepositorioDeCiclosDynamo


@dataclass(frozen=True)
class ReservaTransacional:
    """Grava a reserva no ciclo e no pedido em uma única transação.

    Sem atomicidade aqui, uma falha entre as duas gravações deixaria uma **reserva
    órfã**: o ciclo com uma frase reservada que pedido nenhum conhece. Nada a
    liberaria, e como `Ciclo.esgotado` exige ausência de reservas, o ciclo nunca
    reiniciaria — o bot pararia de entregar frases em silêncio, para sempre.

    Os dois itens vivem na mesma tabela, então uma transação do DynamoDB resolve.
    """

    tabela: Any

    def efetivar(self, pedido: Pedido, ciclo: Ciclo) -> None:
        nome = self.tabela.name
        self.tabela.meta.client.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": nome,
                        "Item": RepositorioDeCiclosDynamo.item_de(ciclo),
                    }
                },
                {
                    "Update": {
                        "TableName": nome,
                        "Key": {"pk": f"pedido#{pedido.identidade}", "sk": "pedido"},
                        "UpdateExpression": "SET estado = :e, frase_reservada = :f",
                        "ExpressionAttributeValues": {
                            ":e": pedido.estado.value,
                            ":f": pedido.frase_reservada or "",
                        },
                        "ConditionExpression": "attribute_exists(pk)",
                    }
                },
            ]
        )
