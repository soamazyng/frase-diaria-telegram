import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar
from uuid import uuid4

from frase_diaria.dominio.colecao import (
    ColecaoValida,
    Diagnostico,
    FrasePreservada,
    SnapshotPersistido,
    TentativaDeSincronizacao,
)
from frase_diaria.dominio.conteudo import Bloco, Trecho
from frase_diaria.dominio.tempo import em_utc

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RepositorioDeColecaoDynamo:
    """O snapshot ativo da coleção, em um único item.

    Cabe em um item porque a coleção é pessoal e pequena (dezenas de frases) —
    o mesmo raciocínio já aplicado ao ciclo. `substituir` grava tudo de uma vez:
    uma frase que saiu da coleção não sobra no item depois de uma
    sincronização bem-sucedida que não a trouxe mais, e uma coleção
    legitimamente vazia vira um item com lista vazia, não a ausência do item.
    """

    tabela: Any

    CHAVE: ClassVar[dict[str, str]] = {"pk": "colecao", "sk": "atual"}
    # Item separado do snapshot: uma tentativa que falhou não produz coleção
    # nova, mas precisa ficar visível para `/status` sem sincronizar de novo.
    CHAVE_DA_TENTATIVA: ClassVar[dict[str, str]] = {"pk": "colecao", "sk": "ultima-tentativa"}

    def carregar_ativa(self) -> SnapshotPersistido | None:
        item = self.tabela.get_item(Key=self.CHAVE, ConsistentRead=True).get("Item")
        if item is None:
            return None
        itens = tuple(_frase_de_item(f) for f in item.get("frases", []))
        diagnosticos = tuple(
            Diagnostico(categoria=str(d["categoria"]), descricao=str(d["descricao"]))
            for d in item.get("diagnosticos", [])
        )
        instante = em_utc(datetime.fromisoformat(item["instante"]))
        return SnapshotPersistido(
            identificador=str(item["identificador"]),
            colecao=ColecaoValida(itens=itens, diagnosticos=diagnosticos),
            instante=instante,
        )

    def substituir(self, colecao: ColecaoValida, instante: datetime) -> None:
        """Publica o snapshot se `instante` não for mais antigo que o já persistido.

        Duas sincronizações concorrentes podem terminar fora de ordem; sem
        essa condição, a mais antiga sobrescreveria a mais nova por último e
        ressuscitaria, mesmo que momentaneamente, uma frase já excluída. Aceitar
        instantes iguais (não só estritamente maiores) é o que permite uma
        mesma sincronização gravar de novo com o mesmo relógio parado, como em
        teste — só a mais antiga de duas é recusada.
        """
        instante_iso = em_utc(instante).isoformat(timespec="microseconds")
        try:
            self.tabela.put_item(
                Item={
                    **self.CHAVE,
                    "identificador": uuid4().hex,
                    "instante": instante_iso,
                    "resultado": "vazia" if not colecao.itens else "valida",
                    "quantidade": len(colecao.itens),
                    "frases": [_item_de_frase(f) for f in colecao.itens],
                    "diagnosticos": [_item_de_diagnostico(d) for d in colecao.diagnosticos],
                },
                ConditionExpression="attribute_not_exists(instante) OR instante <= :novo",
                ExpressionAttributeValues={":novo": instante_iso},
            )
        except self.tabela.meta.client.exceptions.ConditionalCheckFailedException:
            _log.info("snapshot mais recente já persistido; esta gravação foi descartada")

    def registrar_tentativa(self, tentativa: TentativaDeSincronizacao) -> None:
        item: dict[str, Any] = {
            **self.CHAVE_DA_TENTATIVA,
            "instante": em_utc(tentativa.instante).isoformat(timespec="microseconds"),
        }
        if tentativa.erro is not None:
            item["erro"] = tentativa.erro
        self.tabela.put_item(Item=item)

    def ultima_tentativa(self) -> TentativaDeSincronizacao | None:
        item = self.tabela.get_item(Key=self.CHAVE_DA_TENTATIVA, ConsistentRead=True).get("Item")
        if item is None:
            return None
        return TentativaDeSincronizacao(
            instante=em_utc(datetime.fromisoformat(item["instante"])),
            erro=item.get("erro"),
        )


def _item_de_diagnostico(diagnostico: Diagnostico) -> dict[str, Any]:
    return {"categoria": diagnostico.categoria, "descricao": diagnostico.descricao}


def _item_de_frase(frase: FrasePreservada) -> dict[str, Any]:
    return {
        "identidade": frase.identidade,
        "blocos": [_item_de_bloco(b) for b in frase.blocos],
        "discussoes": list(frase.discussoes),
    }


def _frase_de_item(item: dict[str, Any]) -> FrasePreservada:
    return FrasePreservada(
        identidade=str(item["identidade"]),
        blocos=tuple(_bloco_de_item(b) for b in item.get("blocos", [])),
        discussoes=tuple(item.get("discussoes", [])),
    )


def _item_de_bloco(bloco: Bloco) -> dict[str, Any]:
    return {"tipo": bloco.tipo, "trechos": [_item_de_trecho(t) for t in bloco.trechos]}


def _bloco_de_item(item: dict[str, Any]) -> Bloco:
    return Bloco(
        tipo=str(item["tipo"]), trechos=tuple(_trecho_de_item(t) for t in item.get("trechos", []))
    )


def _item_de_trecho(trecho: Trecho) -> dict[str, Any]:
    return {
        "texto": trecho.texto,
        "negrito": trecho.negrito,
        "italico": trecho.italico,
        "tachado": trecho.tachado,
        "sublinhado": trecho.sublinhado,
        "codigo": trecho.codigo,
        "link": trecho.link,
    }


def _trecho_de_item(item: dict[str, Any]) -> Trecho:
    return Trecho(
        texto=str(item["texto"]),
        negrito=bool(item.get("negrito")),
        italico=bool(item.get("italico")),
        tachado=bool(item.get("tachado")),
        sublinhado=bool(item.get("sublinhado")),
        codigo=bool(item.get("codigo")),
        link=item.get("link"),
    )
