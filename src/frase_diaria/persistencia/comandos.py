from dataclasses import dataclass
from datetime import datetime
from typing import Any

from frase_diaria.dominio.atualizacao import Atualizacao


@dataclass(frozen=True)
class RepositorioDeComandosDynamo:
    """Registro idempotente de comandos recebidos pelo webhook.

    A identidade de um extra é o `update_id` do Telegram (spec, 4.6). A
    idempotência vem de uma escrita condicional: se o item já existe, o
    DynamoDB recusa a gravação e o comando é reconhecido como já conhecido.
    Ler antes de gravar não serviria — duas execuções simultâneas leriam
    "não existe" e ambas gravariam.
    """

    tabela: Any

    def registrar(self, atualizacao: Atualizacao, instante: datetime) -> bool:
        try:
            self.tabela.put_item(
                Item={
                    "pk": f"comando#{atualizacao.update_id}",
                    "sk": "registro",
                    "update_id": atualizacao.update_id,
                    "comando": atualizacao.comando.value,
                    "chat_id": atualizacao.conversa.chat_id,
                    "recebido_em": instante.isoformat(),
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
        except self.tabela.meta.client.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def reivindicar_acao(self, update_id: int) -> bool:
        try:
            self.tabela.update_item(
                Key={"pk": f"comando#{update_id}", "sk": "registro"},
                UpdateExpression="SET acao_estado = :iniciada",
                ConditionExpression="attribute_exists(pk) AND attribute_not_exists(acao_estado)",
                ExpressionAttributeValues={":iniciada": "iniciada"},
            )
        except self.tabela.meta.client.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def liberar_acao(self, update_id: int) -> None:
        self.tabela.update_item(
            Key={"pk": f"comando#{update_id}", "sk": "registro"},
            UpdateExpression="REMOVE acao_estado",
            ConditionExpression="acao_estado = :iniciada",
            ExpressionAttributeValues={":iniciada": "iniciada"},
        )

    def marcar_acao_concluida(self, update_id: int) -> None:
        self.tabela.update_item(
            Key={"pk": f"comando#{update_id}", "sk": "registro"},
            UpdateExpression="SET acao_estado = :concluida",
            ConditionExpression="acao_estado = :iniciada",
            ExpressionAttributeValues={":iniciada": "iniciada", ":concluida": "concluida"},
        )
