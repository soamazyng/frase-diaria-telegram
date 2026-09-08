from dataclasses import dataclass
from typing import Any

from frase_diaria.aplicacao.portas import ConflitoDeConcorrencia
from frase_diaria.dominio.ciclo import Ciclo
from frase_diaria.dominio.pedido import Pedido
from frase_diaria.persistencia.ciclos import RepositorioDeCiclosDynamo
from frase_diaria.persistencia.pedidos import RepositorioDePedidosDynamo


@dataclass(frozen=True)
class ReservaTransacional:
    """Grava a reserva no ciclo e no pedido em uma única transação.

    Sem atomicidade aqui, uma falha entre as duas gravações deixaria uma **reserva
    órfã**: o ciclo com uma frase reservada que pedido nenhum conhece. Nada a
    liberaria, e como `Ciclo.esgotado` exige ausência de reservas, o ciclo nunca
    reiniciaria — o bot pararia de entregar frases em silêncio, para sempre.

    Os dois itens vivem na mesma tabela, então uma transação do DynamoDB resolve.
    A condição no ciclo (versão) e no pedido (estado e lease) faz da mesma
    transação o ponto único onde dois executores concorrentes disputam a
    reserva: só um dos dois confirma.
    """

    tabela: Any
    bot_legado: str | None = None

    def efetivar(
        self, pedido: Pedido, ciclo: Ciclo, versao_anterior_do_ciclo: int, sequencial: int
    ) -> None:
        nome = self.tabela.name
        try:
            self.tabela.meta.client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": nome,
                            "Item": RepositorioDeCiclosDynamo.item_de(
                                ciclo, versao_anterior_do_ciclo + 1
                            ),
                            "ConditionExpression": (
                                "attribute_not_exists(versao) OR versao = :versao_esperada"
                            ),
                            "ExpressionAttributeValues": {
                                ":versao_esperada": versao_anterior_do_ciclo
                            },
                        }
                    },
                    {
                        "Update": {
                            "TableName": nome,
                            "Key": {
                                "pk": RepositorioDePedidosDynamo(
                                    self.tabela, bot_legado=self.bot_legado
                                ).chave_do_pedido(pedido.identidade),
                                "sk": "pedido",
                            },
                            "UpdateExpression": (
                                "SET estado = :e, estado_atual = :atual, "
                                "frase_reservada = :f, motivo_do_estado = :m, "
                                "lease_dono = :seq"
                            ),
                            "ExpressionAttributeValues": {
                                ":e": pedido.estado_legado,
                                ":atual": pedido.estado.value,
                                ":f": pedido.frase_reservada or "",
                                ":m": pedido.motivo_do_estado,
                                ":pendente": "pendente",
                                ":aguardando": "aguardando_tentativa",
                                ":seq": sequencial,
                            },
                            "ConditionExpression": (
                                "attribute_exists(pk) AND estado IN (:pendente, :aguardando) "
                                "AND (attribute_not_exists(lease_dono) OR lease_dono = :seq)"
                            ),
                        }
                    },
                ]
            )
        except self.tabela.meta.client.exceptions.TransactionCanceledException as cancelada:
            motivos = getattr(cancelada, "response", {}).get("CancellationReasons", [])
            if any(motivo.get("Code") == "ConditionalCheckFailed" for motivo in motivos):
                raise ConflitoDeConcorrencia(
                    "ciclo ou lease do pedido foram alterados por outro executor"
                ) from None
            raise
