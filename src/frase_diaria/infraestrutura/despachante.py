import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DespachanteLambda:
    """Acorda o worker por invocação assíncrona.

    O payload leva só a identidade do pedido: o worker relê o estado da
    persistência, de modo que um despacho atrasado nunca processe um retrato
    velho do pedido.
    """

    nome_da_funcao: str
    cliente: Any

    def acordar(self, identidade: str) -> None:
        self.cliente.invoke(
            FunctionName=self.nome_da_funcao,
            InvocationType="Event",
            Payload=json.dumps({"pedido": identidade}).encode("utf-8"),
        )
