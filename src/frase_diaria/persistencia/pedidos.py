from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from boto3.dynamodb.conditions import Key

from frase_diaria.aplicacao.diagnostico import erro_sanitizado
from frase_diaria.aplicacao.portas import (
    ChaveDeParte,
    ConfirmacaoDeParte,
    ConflitoDeConcorrencia,
    IncertezaDeParte,
    IntencaoDeParte,
)
from frase_diaria.dominio.pedido import EstadoDoPedido, Origem, Pedido
from frase_diaria.dominio.tempo import em_utc


@dataclass(frozen=True)
class RepositorioDePedidosDynamo:
    """Pedidos, partes entregues e tentativas.

    Um pedido ocupa vários itens sob a mesma partição:

    - `sk = "pedido"` — o estado corrente
    - `sk = "parte#<destinatario>#NNN"` — uma parte confirmada, com o texto
      enviado (v2: por destinatário, já que a mesma parte pode ter desfechos
      diferentes por pessoa)
    - `sk = "tentativa#<sequencial>"` — o histórico de execuções

    Manter partes e tentativas fora do item do pedido é o que impede um item de
    crescer sem limite: o histórico não expira, e o teto de 400 KB do DynamoDB
    chegaria antes do fim do projeto.
    """

    tabela: Any
    versao: str = "desenvolvimento"
    bot_legado: str | None = None

    def _identidade_legada(self, identidade: str) -> str | None:
        if self.bot_legado is not None and identidade.startswith(f"extra#{self.bot_legado}#"):
            return "extra#" + identidade.rsplit("#", 1)[-1]
        return None

    def chave_do_pedido(self, identidade: str) -> str:
        """Chave compartilhada pelas escritas transacionais e pelo repositório."""
        return f"pedido#{self._identidade_legada(identidade) or identidade}"

    def criar_se_ausente(self, pedido: Pedido, instante: datetime) -> bool:
        """Cria o pedido. Devolve False se a identidade já existia.

        Escrita condicional, e não leitura seguida de escrita: um `/frase`
        reentregue pelo Telegram chega concorrente com o original.
        """
        try:
            self.tabela.put_item(
                Item={
                    "pk": self.chave_do_pedido(pedido.identidade),
                    "sk": "pedido",
                    "identidade": self._identidade_legada(pedido.identidade) or pedido.identidade,
                    "identidade_atual": pedido.identidade,
                    "origem": pedido.origem.value,
                    "destinatarios": list(pedido.destinatarios),
                    "estado": pedido.estado_legado,
                    "estado_atual": pedido.estado.value,
                    "motivo_do_estado": pedido.motivo_do_estado,
                    "criado_em": em_utc(instante).isoformat(timespec="microseconds"),
                    "tentativa_unica": pedido.tentativa_unica,
                    "total_de_partes": pedido.total_de_partes,
                    "partes_reservadas": list(pedido.partes_reservadas or ()),
                    "destinatarios_com_falha": list(pedido.destinatarios_com_falha),
                    **(
                        {}
                        if pedido.estado.terminal
                        else {
                            "pendencia": "pedidos",
                            "processar_em": em_utc(pedido.proxima_tentativa or instante).isoformat(
                                timespec="microseconds"
                            ),
                        }
                    ),
                    **(
                        {"prazo": em_utc(pedido.prazo).isoformat(timespec="microseconds")}
                        if pedido.prazo is not None
                        else {}
                    ),
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
        except self.tabela.meta.client.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def obter(self, identidade: str) -> Pedido | None:
        item = self.tabela.get_item(
            Key={"pk": self.chave_do_pedido(identidade), "sk": "pedido"},
            ConsistentRead=True,
        ).get("Item")
        if item is None:
            return None
        destinatarios_gravados = item.get("destinatarios")
        destinatarios = (
            tuple(int(d) for d in destinatarios_gravados)
            if destinatarios_gravados is not None
            # Formato anterior à v2: um único destinatário, gravado como
            # `chat_id` — mesmo padrão de compatibilidade que `bot_legado`.
            else (int(item["chat_id"]),)
        )
        pedido = Pedido(
            identidade=str(item.get("identidade_atual", item["identidade"])),
            origem=Origem(item["origem"]),
            destinatarios=destinatarios,
            estado=EstadoDoPedido(item.get("estado_atual", item["estado"])),
            frase_reservada=item.get("frase_reservada") or None,
            motivo_do_estado=str(item.get("motivo_do_estado") or "estado legado"),
            proxima_tentativa=(
                em_utc(datetime.fromisoformat(item["processar_em"]))
                if item.get("processar_em")
                else None
            ),
            prazo=(em_utc(datetime.fromisoformat(item["prazo"])) if item.get("prazo") else None),
            tentativa_unica=bool(item.get("tentativa_unica", False)),
            total_de_partes=(
                int(item["total_de_partes"]) if item.get("total_de_partes") is not None else None
            ),
            partes_reservadas=(
                tuple(str(parte) for parte in item["partes_reservadas"])
                if item.get("partes_reservadas")
                else None
            ),
            destinatarios_com_falha=tuple(int(d) for d in item.get("destinatarios_com_falha", [])),
        )
        # Uma versão antiga pode avançar o estado sem conhecer estado_atual.
        if pedido.estado_legado != item["estado"]:
            pedido = replace(
                pedido, estado=EstadoDoPedido(item["estado"]), motivo_do_estado="estado legado"
            )
        return pedido

    def salvar(self, pedido: Pedido, sequencial: int | None = None) -> None:
        """Atualiza um pedido existente.

        A condição impede o upsert que o `update_item` faria por padrão: salvar o
        estado de um pedido nunca criado o inventaria na tabela. Quando
        `sequencial` é informado, ele precisa ser o dono do lease vigente — é o
        que impede um executor cujo lease já foi transferido de confirmar um
        estado (ticket 09).
        """
        valores: dict[str, Any] = {
            ":e": pedido.estado_legado,
            ":atual": pedido.estado.value,
            ":m": pedido.motivo_do_estado,
            ":f": pedido.frase_reservada or "",
            ":i": self._identidade_legada(pedido.identidade) or pedido.identidade,
            ":identidade_atual": pedido.identidade,
            ":o": pedido.origem.value,
            ":d": list(pedido.destinatarios),
            ":total": pedido.total_de_partes,
            ":partes": list(pedido.partes_reservadas or ()),
            ":falhos": list(pedido.destinatarios_com_falha),
        }
        expressao = (
            "SET estado = :e, estado_atual = :atual, motivo_do_estado = :m, frase_reservada = :f, "
            "identidade_atual = :identidade_atual, "
            "identidade = :i, origem = :o, destinatarios = :d, total_de_partes = :total"
            ", partes_reservadas = :partes, destinatarios_com_falha = :falhos"
        )
        if pedido.estado.terminal:
            expressao += " REMOVE pendencia, processar_em"
        else:
            valores[":p"] = "pedidos"
            expressao += ", pendencia = :p"
            if pedido.proxima_tentativa is not None:
                valores[":t"] = em_utc(pedido.proxima_tentativa).isoformat(timespec="microseconds")
                expressao += ", processar_em = :t"
            else:
                expressao += ", processar_em = if_not_exists(processar_em, criado_em)"
        terminais = [estado for estado in EstadoDoPedido if estado.terminal]
        for indice, estado in enumerate(terminais):
            valores[f":terminal{indice}"] = estado.value
        condicao = (
            "attribute_exists(pk) AND NOT estado IN ("
            + ", ".join(f":terminal{i}" for i in range(len(terminais)))
            + ")"
        )
        if sequencial is not None:
            valores[":lease"] = sequencial
            condicao += " AND (attribute_not_exists(lease_dono) OR lease_dono = :lease)"
        try:
            self.tabela.update_item(
                Key={"pk": self.chave_do_pedido(pedido.identidade), "sk": "pedido"},
                UpdateExpression=expressao,
                ExpressionAttributeValues=valores,
                ConditionExpression=condicao,
            )
        except self.tabela.meta.client.exceptions.ConditionalCheckFailedException:
            if sequencial is None:
                raise
            # A condição reúne dois motivos possíveis — o pedido já chegou a um
            # estado terminal, ou o lease já foi transferido — e os dois dizem a
            # mesma coisa para quem chama: outro executor já avançou o pedido.
            raise ConflitoDeConcorrencia("outro executor já avançou este pedido") from None

    def assumir_lease(
        self, pedido: str, sequencial: int, agora: datetime, duracao: timedelta
    ) -> None:
        """Reivindica a exclusividade sobre o envio deste pedido por tempo limitado.

        Um `sequencial` vem de `registrar_tentativa`, que já é atômico e
        monotônico: nenhum outro executor pode ter obtido um valor maior antes
        deste, então a reivindicação de um lease inexistente, mais antigo ou
        igual ao próprio sempre pode prosseguir — a igualdade é o que torna a
        chamada idempotente: um retry automático do SDK sobre a mesma
        tentativa, depois que a primeira já teve sucesso, não pode ser
        recusado como se fosse de outro executor. Falha apenas quando outro
        executor já detém um lease **mais novo** — sinal de que esta tentativa
        foi superada e não deve prosseguir a enviar nem confirmar nada (AC03).
        Um lease vencido pode ser assumido por qualquer sequencial, o que
        evita bloqueio permanente após uma queda (ticket 09).
        """
        agora_utc = em_utc(agora)
        expira_em = agora_utc + duracao
        try:
            self.tabela.update_item(
                Key={"pk": self.chave_do_pedido(pedido), "sk": "pedido"},
                UpdateExpression="SET lease_dono = :seq, lease_expira_em = :exp",
                ConditionExpression=(
                    "attribute_exists(pk) AND ("
                    "attribute_not_exists(lease_dono) OR lease_dono <= :seq "
                    "OR lease_expira_em <= :agora)"
                ),
                ExpressionAttributeValues={
                    ":seq": sequencial,
                    ":exp": expira_em.isoformat(timespec="microseconds"),
                    ":agora": agora_utc.isoformat(timespec="microseconds"),
                },
            )
        except self.tabela.meta.client.exceptions.ConditionalCheckFailedException:
            raise ConflitoDeConcorrencia("lease do pedido pertence a outro executor") from None

    @staticmethod
    def _chave_da_parte(destinatario: int, indice: int) -> str:
        """v2: a mesma parte pode ter desfechos diferentes por destinatário,
        então o destinatário faz parte da chave — não só o índice."""
        return f"parte#{destinatario}#{indice:03d}"

    @staticmethod
    def _item_do_indice_de_envio(pedido: str, destinatario: int) -> dict[str, Any] | None:
        if not pedido.startswith("diaria#"):
            return None
        try:
            dia = date.fromisoformat(pedido.rsplit("#", 1)[-1])
        except ValueError:
            return None
        return {
            "pk": f"status#{destinatario}",
            "sk": f"diaria#{dia.isoformat()}",
            "pedido": pedido,
        }

    def registrar_intencao_parte(self, intencao: IntencaoDeParte) -> None:
        """Registra a intenção de enviar uma parte antes do envio externo.

        A intenção é um rastro operacional: se o processo cair antes da confirmação,
        as próximas leituras podem distinguir "nunca confirmado" de "confirmado".
        """
        nome = self.tabela.name
        chave = intencao.chave
        sequencial = intencao.tentativa.sequencial
        if sequencial is None:
            raise ValueError("intenção de envio exige sequencial")
        item = {
            "pk": self.chave_do_pedido(chave.pedido),
            "sk": self._chave_da_parte(chave.destinatario, chave.indice),
            "indice": chave.indice,
            "destinatario": chave.destinatario,
            "identidade": Pedido.identidade_de_parte(
                chave.pedido, chave.destinatario, chave.indice
            ),
            "texto": intencao.texto,
            "estado": "intencao",
            "intencao_em": em_utc(intencao.tentativa.instante).isoformat(timespec="microseconds"),
        }
        try:
            self.tabela.meta.client.transact_write_items(
                TransactItems=[
                    {
                        "ConditionCheck": {
                            "TableName": nome,
                            "Key": {"pk": self.chave_do_pedido(chave.pedido), "sk": "pedido"},
                            "ConditionExpression": "attribute_exists(pk) AND lease_dono = :seq",
                            "ExpressionAttributeValues": {":seq": sequencial},
                        }
                    },
                    {
                        "Put": {
                            "TableName": nome,
                            "Item": item,
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                ]
            )
        except self.tabela.meta.client.exceptions.TransactionCanceledException:
            raise ConflitoDeConcorrencia("pedido ou parte avançaram em outro executor") from None

    def descartar_intencao_parte(self, chave: ChaveDeParte, sequencial: int) -> None:
        """Remove uma intenção somente após rejeição inequívoca do provedor."""
        nome = self.tabela.name
        try:
            self.tabela.meta.client.transact_write_items(
                TransactItems=[
                    {
                        "ConditionCheck": {
                            "TableName": nome,
                            "Key": {"pk": self.chave_do_pedido(chave.pedido), "sk": "pedido"},
                            "ConditionExpression": "attribute_exists(pk) AND lease_dono = :seq",
                            "ExpressionAttributeValues": {":seq": sequencial},
                        }
                    },
                    {
                        "Delete": {
                            "TableName": nome,
                            "Key": {
                                "pk": self.chave_do_pedido(chave.pedido),
                                "sk": self._chave_da_parte(chave.destinatario, chave.indice),
                            },
                            "ConditionExpression": "#estado = :intencao",
                            "ExpressionAttributeNames": {"#estado": "estado"},
                            "ExpressionAttributeValues": {":intencao": "intencao"},
                        }
                    },
                ]
            )
        except self.tabela.meta.client.exceptions.TransactionCanceledException:
            raise ConflitoDeConcorrencia("pedido ou parte avançaram em outro executor") from None

    def confirmar_parte(self, confirmacao: ConfirmacaoDeParte) -> None:
        """Registra uma parte como entregue, com o texto que foi de fato enviado.

        Guardar o texto — e não uma referência à frase — é o que preserva o
        histórico quando a origem muda depois (spec, 4.8). Quando `sequencial` é
        informado, a confirmação só vale se ainda for o dono do lease: é a
        garantia de que um executor superado não confirma entrega (AC03).
        """
        chave = confirmacao.chave
        item = {
            "pk": self.chave_do_pedido(chave.pedido),
            "sk": self._chave_da_parte(chave.destinatario, chave.indice),
            "indice": chave.indice,
            "destinatario": chave.destinatario,
            "identidade": Pedido.identidade_de_parte(
                chave.pedido, chave.destinatario, chave.indice
            ),
            "texto": confirmacao.conteudo.texto,
            "message_id": confirmacao.conteudo.message_id,
            "estado": "confirmada",
            "confirmada_em": em_utc(confirmacao.tentativa.instante).isoformat(
                timespec="microseconds"
            ),
        }
        indice_de_envio = self._item_do_indice_de_envio(chave.pedido, chave.destinatario)
        sequencial = confirmacao.tentativa.sequencial
        if sequencial is None:
            self.tabela.put_item(Item=item)
            if indice_de_envio is not None:
                self.tabela.put_item(Item=indice_de_envio)
            return
        nome = self.tabela.name
        try:
            transacao = [
                {
                    "ConditionCheck": {
                        "TableName": nome,
                        "Key": {"pk": self.chave_do_pedido(chave.pedido), "sk": "pedido"},
                        "ConditionExpression": (
                            "attribute_not_exists(lease_dono) OR lease_dono = :seq"
                        ),
                        "ExpressionAttributeValues": {":seq": sequencial},
                    }
                },
                {"Put": {"TableName": nome, "Item": item}},
            ]
            if indice_de_envio is not None:
                transacao.append({"Put": {"TableName": nome, "Item": indice_de_envio}})
            self.tabela.meta.client.transact_write_items(TransactItems=transacao)
        except self.tabela.meta.client.exceptions.TransactionCanceledException:
            raise ConflitoDeConcorrencia("lease do pedido pertence a outro executor") from None

    def marcar_parte_incerta(self, incerteza: IncertezaDeParte) -> None:
        """Converte somente uma intenção, mantendo o conteúdo e o dono vigente."""
        nome = self.tabela.name
        chave = incerteza.chave
        sequencial = incerteza.tentativa.sequencial
        if sequencial is None:
            raise ValueError("incerteza de envio exige sequencial")
        indice_de_envio = self._item_do_indice_de_envio(chave.pedido, chave.destinatario)
        try:
            transacao = [
                {
                    "ConditionCheck": {
                        "TableName": nome,
                        "Key": {"pk": self.chave_do_pedido(chave.pedido), "sk": "pedido"},
                        "ConditionExpression": "attribute_exists(pk) AND lease_dono = :seq",
                        "ExpressionAttributeValues": {":seq": sequencial},
                    }
                },
                {
                    "Update": {
                        "TableName": nome,
                        "Key": {
                            "pk": self.chave_do_pedido(chave.pedido),
                            "sk": self._chave_da_parte(chave.destinatario, chave.indice),
                        },
                        "UpdateExpression": (
                            "SET #estado = :incerto, motivo = :m, incerta_em = :t"
                        ),
                        "ConditionExpression": "#estado = :intencao",
                        "ExpressionAttributeNames": {"#estado": "estado"},
                        "ExpressionAttributeValues": {
                            ":incerto": "incerto",
                            ":intencao": "intencao",
                            ":m": incerteza.motivo,
                            ":t": em_utc(incerteza.tentativa.instante).isoformat(
                                timespec="microseconds"
                            ),
                        },
                    }
                },
            ]
            if indice_de_envio is not None:
                transacao.append({"Put": {"TableName": nome, "Item": indice_de_envio}})
            self.tabela.meta.client.transact_write_items(TransactItems=transacao)
        except self.tabela.meta.client.exceptions.TransactionCanceledException:
            raise ConflitoDeConcorrencia("pedido ou parte avançaram em outro executor") from None

    def indices_confirmados(self, pedido: str, destinatario: int) -> set[int]:
        return {
            int(item["indice"])
            for item in self._listar_itens(pedido, f"parte#{destinatario}#")
            if item.get("estado") != "incerto"
            and item.get("estado") != "intencao"
            and item.get("message_id") not in (None, 0)
        }

    def indices_incertos(self, pedido: str, destinatario: int) -> set[int]:
        return {
            int(item["indice"])
            for item in self._listar_itens(pedido, f"parte#{destinatario}#")
            if item.get("estado") == "incerto"
        }

    def indices_intencoes(self, pedido: str, destinatario: int) -> set[int]:
        return {
            int(item["indice"])
            for item in self._listar_itens(pedido, f"parte#{destinatario}#")
            if item.get("estado") == "intencao"
        }

    def ultimo_pedido_do_destinatario(self, destinatario: int, antes_de: date) -> Pedido | None:
        resposta = self.tabela.query(
            KeyConditionExpression=Key("pk").eq(f"status#{destinatario}")
            & Key("sk").lt(f"diaria#{antes_de.isoformat()}"),
            ScanIndexForward=False,
            Limit=1,
            ConsistentRead=True,
        )
        itens = resposta.get("Items", [])
        if not itens:
            return None
        return self.obter(str(itens[0]["pedido"]))

    def buscar_vencidos(self, instante: datetime) -> list[Pedido]:
        """Consulta somente pendências; revalida o índice eventualmente consistente."""
        agora = em_utc(instante)
        argumentos: dict[str, Any] = {
            "IndexName": "pendencias",
            "KeyConditionExpression": Key("pendencia").eq("pedidos")
            & Key("processar_em").lte(agora.isoformat(timespec="microseconds")),
        }
        pedidos: list[Pedido] = []
        while True:
            resposta = self.tabela.query(**argumentos)
            for item in resposta.get("Items", []):
                pedido = self.obter(str(item["pk"]).removeprefix("pedido#"))
                if (
                    pedido is not None
                    and not pedido.estado.terminal
                    and pedido.proxima_tentativa is not None
                    and pedido.proxima_tentativa <= agora
                ):
                    pedidos.append(pedido)
            if not resposta.get("LastEvaluatedKey"):
                return pedidos
            argumentos["ExclusiveStartKey"] = resposta["LastEvaluatedKey"]

    def registrar_tentativa(
        self, pedido: str, resultado: str, erro: str | None, instante: datetime
    ) -> int:
        ocorrida_em = em_utc(instante).isoformat(timespec="microseconds")
        contador = self.tabela.update_item(
            Key={"pk": self.chave_do_pedido(pedido), "sk": "sequencia-de-tentativas"},
            UpdateExpression="ADD sequencial :um",
            ExpressionAttributeValues={":um": 1},
            ReturnValues="UPDATED_NEW",
        )
        sequencial = int(contador["Attributes"]["sequencial"])
        self.tabela.put_item(
            Item={
                "pk": self.chave_do_pedido(pedido),
                "sk": f"tentativa#{sequencial:020d}",
                "identidade": Pedido.identidade_de_tentativa(pedido, sequencial),
                "sequencial": sequencial,
                "resultado": resultado,
                "erro": erro_sanitizado(erro),
                "ocorrida_em": ocorrida_em,
                "versao": self.versao,
                "correlacao": uuid4().hex,
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
        return sequencial

    def finalizar_tentativa(
        self, pedido: str, sequencial: int, resultado: str, erro: str | None, instante: datetime
    ) -> None:
        self.tabela.update_item(
            Key={"pk": self.chave_do_pedido(pedido), "sk": f"tentativa#{sequencial:020d}"},
            UpdateExpression="SET resultado = :r, erro = :e, finalizada_em = :t",
            ExpressionAttributeValues={
                ":r": resultado,
                ":e": erro_sanitizado(erro),
                ":t": em_utc(instante).isoformat(timespec="microseconds"),
            },
            ConditionExpression="attribute_exists(pk)",
        )

    def listar_tentativas(self, pedido: str) -> list[dict[str, Any]]:
        """Recupera o histórico, incluindo tentativas anteriores ao ticket 07."""
        return self._listar_itens(pedido, "tentativa#")

    def _listar_itens(self, pedido: str, prefixo: str) -> list[dict[str, Any]]:
        argumentos: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(self.chave_do_pedido(pedido))
            & Key("sk").begins_with(prefixo),
            "ConsistentRead": True,
        }
        itens: list[dict[str, Any]] = []
        while True:
            resposta = self.tabela.query(**argumentos)
            itens.extend(resposta.get("Items", []))
            if not resposta.get("LastEvaluatedKey"):
                return itens
            argumentos["ExclusiveStartKey"] = resposta["LastEvaluatedKey"]
