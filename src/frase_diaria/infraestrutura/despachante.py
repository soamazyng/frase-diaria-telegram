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
        self._invocar({"pedido": identidade})

    def pedir_status(self, chat_id: int) -> None:
        """Pede ao worker que monte e envie o relatório de `/status`.

        Mesma função, payload de formato distinto: `worker_handler` decide
        qual caminho seguir pela chave presente no evento.
        """
        self._invocar({"status_chat_id": chat_id})

    def _invocar(self, payload: dict[str, Any]) -> None:
        self.cliente.invoke(
            FunctionName=self.nome_da_funcao,
            InvocationType="Event",
            Payload=json.dumps(payload).encode("utf-8"),
        )
