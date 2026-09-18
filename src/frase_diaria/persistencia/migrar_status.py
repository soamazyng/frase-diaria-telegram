from __future__ import annotations

import os
from datetime import date
from typing import Any

import boto3


def _entrega_do_item(item: dict[str, Any]) -> tuple[str, int, date] | None:
    identidade = str(item.get("pk", "")).removeprefix("pedido#")
    partes_da_identidade = identidade.split("#")
    if not partes_da_identidade or partes_da_identidade[0] != "diaria":
        return None
    if not str(item.get("sk", "")).startswith("parte#"):
        return None
    estado = item.get("estado")
    confirmada_legada = estado is None and item.get("message_id") not in (None, 0)
    if estado not in {"confirmada", "incerto"} and not confirmada_legada:
        return None
    try:
        dia = date.fromisoformat(partes_da_identidade[-1])
        destinatario = (
            int(item["destinatario"])
            if len(partes_da_identidade) == 2
            else int(partes_da_identidade[-2])
        )
    except (KeyError, TypeError, ValueError):
        return None
    return identidade, destinatario, dia


def indexar_status_legado(tabela: Any) -> int:
    """Cria ponte de consulta para diárias entregues antes do índice de status."""
    entregas: set[tuple[str, int, date]] = set()
    argumentos: dict[str, Any] = {
        "ConsistentRead": True,
        "ProjectionExpression": "pk, sk, #estado, destinatario, message_id",
        "ExpressionAttributeNames": {"#estado": "estado"},
    }
    while True:
        resposta = tabela.scan(**argumentos)
        for item in resposta.get("Items", []):
            if entrega := _entrega_do_item(item):
                entregas.add(entrega)
        if not resposta.get("LastEvaluatedKey"):
            break
        argumentos["ExclusiveStartKey"] = resposta["LastEvaluatedKey"]

    total = 0
    for pedido, destinatario, dia in entregas:
        try:
            tabela.put_item(
                Item={
                    "pk": f"status#{destinatario}",
                    "sk": f"diaria#{dia.isoformat()}",
                    "pedido": pedido,
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
        except tabela.meta.client.exceptions.ConditionalCheckFailedException:
            continue
        total += 1
    return total


def main() -> None:
    tabela = boto3.resource("dynamodb").Table(os.environ["TABELA_ESTADO"])
    total = indexar_status_legado(tabela)
    print(f"{total} índice(s) de status criado(s)")


if __name__ == "__main__":
    main()
