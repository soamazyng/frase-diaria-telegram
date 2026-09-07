from dataclasses import dataclass
from datetime import datetime
from typing import Any

from boto3.dynamodb.conditions import Key

from frase_diaria.dominio.pedido import EstadoDoPedido, Origem, Pedido


@dataclass(frozen=True)
class RepositorioDePedidosDynamo:
    """Pedidos, partes entregues e tentativas.

    Um pedido ocupa vários itens sob a mesma partição:

    - `sk = "pedido"` — o estado corrente
    - `sk = "parte#NNN"` — uma parte confirmada, com o texto enviado
    - `sk = "tentativa#<instante>"` — o histórico de execuções

    Manter partes e tentativas fora do item do pedido é o que impede um item de
    crescer sem limite: o histórico não expira, e o teto de 400 KB do DynamoDB
    chegaria antes do fim do projeto.
    """

    tabela: Any

    @staticmethod
    def _particao(identidade: str) -> str:
        return f"pedido#{identidade}"

    def criar_se_ausente(self, pedido: Pedido, instante: datetime) -> bool:
        """Cria o pedido. Devolve False se a identidade já existia.

        Escrita condicional, e não leitura seguida de escrita: um `/frase`
        reentregue pelo Telegram chega concorrente com o original.
        """
        try:
            self.tabela.put_item(
                Item={
                    "pk": self._particao(pedido.identidade),
                    "sk": "pedido",
                    "identidade": pedido.identidade,
                    "origem": pedido.origem.value,
                    "chat_id": pedido.chat_id,
                    "estado": pedido.estado.value,
                    "criado_em": instante.isoformat(),
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
        except self.tabela.meta.client.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def obter(self, identidade: str) -> Pedido | None:
        item = self.tabela.get_item(Key={"pk": self._particao(identidade), "sk": "pedido"}).get(
            "Item"
        )
        if item is None:
            return None
        return Pedido(
            identidade=str(item["identidade"]),
            origem=Origem(item["origem"]),
            chat_id=int(item["chat_id"]),
            estado=EstadoDoPedido(item["estado"]),
            frase_reservada=item.get("frase_reservada") or None,
        )

    def salvar(self, pedido: Pedido) -> None:
        """Atualiza um pedido existente.

        A condição impede o upsert que o `update_item` faria por padrão: salvar o
        estado de um pedido nunca criado o inventaria na tabela.
        """
        self.tabela.update_item(
            Key={"pk": self._particao(pedido.identidade), "sk": "pedido"},
            UpdateExpression=(
                "SET estado = :e, frase_reservada = :f, "
                "identidade = :i, origem = :o, chat_id = :c"
            ),
            ExpressionAttributeValues={
                ":e": pedido.estado.value,
                ":f": pedido.frase_reservada or "",
                ":i": pedido.identidade,
                ":o": pedido.origem.value,
                ":c": pedido.chat_id,
            },
            ConditionExpression="attribute_exists(pk)",
        )

    def confirmar_parte(
        self, pedido: str, indice: int, texto: str, message_id: int, instante: datetime
    ) -> None:
        """Registra uma parte como entregue, com o texto que foi de fato enviado.

        Guardar o texto — e não uma referência à frase — é o que preserva o
        histórico quando a origem muda depois (spec, 4.8).
        """
        self.tabela.put_item(
            Item={
                "pk": self._particao(pedido),
                "sk": f"parte#{indice:03d}",
                "indice": indice,
                "texto": texto,
                "message_id": message_id,
                "confirmada_em": instante.isoformat(),
            }
        )

    def indices_confirmados(self, pedido: str) -> set[int]:
        resposta = self.tabela.query(
            KeyConditionExpression=Key("pk").eq(self._particao(pedido))
            & Key("sk").begins_with("parte#"),
            ProjectionExpression="indice",
        )
        return {int(item["indice"]) for item in resposta.get("Items", [])}

    def registrar_tentativa(
        self, pedido: str, resultado: str, erro: str | None, instante: datetime
    ) -> None:
        self.tabela.put_item(
            Item={
                "pk": self._particao(pedido),
                "sk": f"tentativa#{instante.isoformat()}",
                "resultado": resultado,
                "erro": erro or "",
                "ocorrida_em": instante.isoformat(),
            }
        )
