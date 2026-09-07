from dataclasses import dataclass
from typing import Any, ClassVar

from frase_diaria.aplicacao.portas import ConflitoDeConcorrencia
from frase_diaria.dominio.ciclo import Ciclo


@dataclass(frozen=True)
class RepositorioDeCiclosDynamo:
    """O ciclo corrente, em um único item.

    Cabe em um item porque o ciclo é limitado pela coleção — algumas dezenas de
    identidades — e zera a cada reinício. Não é o histórico: esse vive nas partes
    e tentativas de cada pedido, que ficam em itens próprios.

    Diárias e extras compartilham este item, então dois executores podem
    carregá-lo ao mesmo tempo. `carregar` devolve a versão lida junto com o
    ciclo; `salvar` exige essa versão de volta e recusa a gravação se ela não
    for mais a vigente — quem perde a corrida recebe `ConflitoDeConcorrencia`
    em vez de sobrescrever silenciosamente a reserva ou o consumo do outro.
    """

    tabela: Any

    CHAVE: ClassVar[dict[str, str]] = {"pk": "ciclo", "sk": "atual"}

    def carregar(self) -> tuple[Ciclo, int]:
        item = self.tabela.get_item(Key=self.CHAVE, ConsistentRead=True).get("Item")
        if item is None:
            return Ciclo.primeiro(), 0
        ciclo = Ciclo(
            numero=int(item["numero"]),
            consumidas=frozenset(item.get("consumidas") or ()),
            reservadas=frozenset(item.get("reservadas") or ()),
            consumidas_com_ressalva=frozenset(item.get("com_ressalva") or ()),
            ultima_entregue=item.get("ultima_entregue") or None,
            entregas_neste_ciclo=int(item.get("entregas", 0)),
        )
        return ciclo, int(item.get("versao", 0))

    @classmethod
    def item_de(cls, ciclo: Ciclo, versao: int) -> dict[str, Any]:
        """Serializa o ciclo na versão dada. Compartilhado com a gravação transacional."""
        item: dict[str, Any] = {
            **cls.CHAVE,
            "numero": ciclo.numero,
            "ultima_entregue": ciclo.ultima_entregue or "",
            "entregas": ciclo.entregas_neste_ciclo,
            "versao": versao,
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

    def salvar(self, ciclo: Ciclo, versao_anterior: int) -> None:
        """Grava o ciclo se `versao_anterior` ainda for a versão vigente.

        `attribute_not_exists(versao)` cobre a primeira gravação de sempre, onde
        `versao_anterior` é 0 e o item ainda não existe.
        """
        try:
            self.tabela.put_item(
                Item=self.item_de(ciclo, versao_anterior + 1),
                ConditionExpression="attribute_not_exists(versao) OR versao = :esperada",
                ExpressionAttributeValues={":esperada": versao_anterior},
            )
        except self.tabela.meta.client.exceptions.ConditionalCheckFailedException:
            raise ConflitoDeConcorrencia("ciclo foi alterado por outro executor") from None
