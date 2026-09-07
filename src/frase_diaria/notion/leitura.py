from dataclasses import dataclass
from typing import Any, Protocol

from frase_diaria.dominio.colecao import (
    ColecaoValida,
    Diagnostico,
    FrasePreservada,
    SincronizacaoIncompleta,
)
from frase_diaria.dominio.conteudo import Bloco, Trecho
from frase_diaria.notion.cliente import ErroDoNotion

TIPO_ITEM_NUMERADO = "numbered_list_item"
TIPO_SUBPAGINA = "child_page"


class ClienteNotion(Protocol):
    """O que a leitura precisa do Notion — busca de blocos e de discussões.

    `buscar_comentarios` devolve `None` quando o acesso for negado: é o que
    permite tratar a limitação como diagnóstico, não como falha da coleção.
    """

    def buscar_filhos(self, bloco_id: str) -> tuple[dict[str, Any], ...]: ...
    def buscar_comentarios(self, bloco_id: str) -> tuple[dict[str, Any], ...] | None: ...


@dataclass(frozen=True)
class LeitorDeColecao:
    """Converte a árvore de blocos do Notion na coleção válida do domínio.

    Publica um resultado somente depois de percorrer toda a paginação e todos
    os descendentes: qualquer falha no meio do caminho vira
    `SincronizacaoIncompleta`, nunca uma coleção truncada (spec, 4.2; AC08).
    """

    cliente: ClienteNotion

    def ler(self, pagina_id: str) -> ColecaoValida:
        try:
            filhos_do_topo = self.cliente.buscar_filhos(pagina_id)
        except ErroDoNotion as erro:
            raise SincronizacaoIncompleta(str(erro)) from erro

        itens: list[FrasePreservada] = []
        diagnosticos: list[Diagnostico] = []
        for bloco in filhos_do_topo:
            tipo = bloco.get("type")
            if tipo == TIPO_SUBPAGINA:
                # Subpáginas e o projeto inteiro são apenas mais uma subpágina.
                continue
            if tipo != TIPO_ITEM_NUMERADO:
                descricao = f"bloco {bloco.get('id')} solto no nível da coleção (tipo {tipo!r})"
                diagnosticos.append(Diagnostico(categoria="conteudo_solto", descricao=descricao))
                continue

            trechos_do_item = _trechos_de(bloco)
            if not trechos_do_item:
                # AC10: item vazio não vira frase — nem sequer é diagnóstico.
                continue

            try:
                descendentes = self._ler_descendentes(bloco) if bloco.get("has_children") else ()
            except ErroDoNotion as erro:
                raise SincronizacaoIncompleta(str(erro)) from erro

            blocos = (Bloco(tipo=tipo, trechos=trechos_do_item), *descendentes)
            discussoes = self._ler_discussoes(bloco["id"], diagnosticos)
            frase = FrasePreservada(identidade=bloco["id"], blocos=blocos, discussoes=discussoes)
            itens.append(frase)

        return ColecaoValida(itens=tuple(itens), diagnosticos=tuple(diagnosticos))

    def _ler_descendentes(self, bloco: dict[str, Any]) -> tuple[Bloco, ...]:
        """Percorre os filhos de um bloco, recursivamente, na ordem da página.

        Nenhum tipo aqui vira frase independente — inclusive uma lista
        numerada aninhada é só conteúdo da frase que a contém (spec, 4.2).
        """
        resultado: list[Bloco] = []
        for filho in self.cliente.buscar_filhos(bloco["id"]):
            tipo = str(filho.get("type", ""))
            if tipo == TIPO_SUBPAGINA:
                continue
            resultado.append(Bloco(tipo=tipo, trechos=_trechos_de(filho)))
            if filho.get("has_children"):
                resultado.extend(self._ler_descendentes(filho))
        return tuple(resultado)

    def _ler_discussoes(self, bloco_id: str, diagnosticos: list[Diagnostico]) -> tuple[str, ...]:
        try:
            comentarios = self.cliente.buscar_comentarios(bloco_id)
        except ErroDoNotion as erro:
            # Acesso negado (403) já vira `None` dentro do cliente; o que chega
            # aqui como exceção é falha de rede, timeout ou erro do servidor —
            # o mesmo tratamento dos outros dois pontos de leitura.
            raise SincronizacaoIncompleta(str(erro)) from erro
        if comentarios is None:
            diagnosticos.append(
                Diagnostico(
                    categoria="acesso_negado",
                    descricao=f"sem acesso às discussões do bloco {bloco_id}",
                )
            )
            return ()
        return tuple(_texto_simples(comentario.get("rich_text", [])) for comentario in comentarios)


def _trechos_de(bloco: dict[str, Any]) -> tuple[Trecho, ...]:
    tipo = bloco.get("type")
    conteudo = bloco.get(tipo, {}) if tipo else {}
    return tuple(
        Trecho(
            texto=item.get("plain_text", ""),
            negrito=bool(item.get("annotations", {}).get("bold")),
            italico=bool(item.get("annotations", {}).get("italic")),
            tachado=bool(item.get("annotations", {}).get("strikethrough")),
            sublinhado=bool(item.get("annotations", {}).get("underline")),
            codigo=bool(item.get("annotations", {}).get("code")),
            link=item.get("href"),
        )
        for item in conteudo.get("rich_text", [])
    )


def _texto_simples(rich_text: list[dict[str, Any]]) -> str:
    return "".join(item.get("plain_text", "") for item in rich_text)
