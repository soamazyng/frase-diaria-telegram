from __future__ import annotations

from typing import Any


def indexar_pedidos_legados(tabela: Any) -> int:
    """Adota pedidos legados ao índice de pendências.

    Itens antigos do DynamoDB podem existir sem o atributo de índice
    ``pendencia``/``processar_em`` que o worker moderno usa para consultar
    pendências em andamento. A migração percorre a tabela em páginas, indexa
    apenas pedidos de estado não terminal e torna a operação idempotente.
    """
    total = 0
    argumentos: dict[str, Any] = {"ConsistentRead": True}

    while True:
        resposta = tabela.scan(**argumentos)
        for item in resposta.get("Items", []):
            if item.get("sk") != "pedido":
                continue
            if item.get("pendencia") is not None:
                continue

            estado = str(item.get("estado_atual") or item.get("estado") or "")
            if estado in {"enviado", "parcial", "incerto", "falhou", "expirado"}:
                continue
            if not estado:
                continue

            processar_em = item.get("processar_em") or item.get("criado_em")
            if processar_em is None:
                continue

            try:
                tabela.update_item(
                    Key={"pk": item["pk"], "sk": item["sk"]},
                    UpdateExpression="SET pendencia = :p, processar_em = :t",
                    ExpressionAttributeValues={":p": "pedidos", ":t": processar_em},
                    ConditionExpression="attribute_not_exists(pendencia)",
                )
            except Exception as erro:  # pragma: no cover - depende do cliente DynamoDB
                codigo = getattr(erro, "response", {}).get("Error", {}).get("Code")
                if codigo != "ConditionalCheckFailedException":
                    raise
                continue
            total += 1

        if not resposta.get("LastEvaluatedKey"):
            return total

        argumentos["ExclusiveStartKey"] = resposta["LastEvaluatedKey"]
