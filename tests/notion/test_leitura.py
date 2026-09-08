"""A leitura decide o que é frase, o que é descendente e o que é ruído.

Regras da spec 4.2 exercitadas aqui: só item numerado preenchido do nível da
coleção vira frase; subpágina (inclusive "o projeto inteiro") é ignorada;
lista numerada interna não cria frase independente; conteúdo solto vira
diagnóstico; leitura incompleta nunca vira coleção vazia.
"""

from typing import Any

import pytest

from frase_diaria.dominio.colecao import SincronizacaoIncompleta
from frase_diaria.notion.cliente import ErroDoNotion
from frase_diaria.notion.leitura import LeitorDeColecao

PAGINA = "pagina-colecao"


def _rich_text(texto: str, href: str | None = None, **anotacoes: Any) -> list[dict[str, Any]]:
    base = {
        "bold": False,
        "italic": False,
        "strikethrough": False,
        "underline": False,
        "code": False,
    }
    base.update(anotacoes)
    return [{"plain_text": texto, "href": href, "annotations": base}]


def _numerado(id_: str, texto: str, *, tem_filhos: bool = False) -> dict[str, Any]:
    return {
        "id": id_,
        "type": "numbered_list_item",
        "has_children": tem_filhos,
        "numbered_list_item": {"rich_text": _rich_text(texto) if texto else []},
    }


def _paragrafo(id_: str, texto: str, *, tem_filhos: bool = False) -> dict[str, Any]:
    return {
        "id": id_,
        "type": "paragraph",
        "has_children": tem_filhos,
        "paragraph": {"rich_text": _rich_text(texto)},
    }


def _subpagina(id_: str) -> dict[str, Any]:
    return {"id": id_, "type": "child_page", "has_children": True, "child_page": {"title": "x"}}


class ClienteFalso:
    def __init__(
        self,
        filhos: dict[str, list[dict[str, Any]]],
        comentarios: dict[str, list[dict[str, Any]] | None] | None = None,
    ) -> None:
        self.filhos = filhos
        self.comentarios = comentarios or {}
        self.chamadas_de_filhos: list[str] = []

    def buscar_filhos(self, bloco_id: str) -> tuple[dict[str, Any], ...]:
        self.chamadas_de_filhos.append(bloco_id)
        if bloco_id not in self.filhos:
            raise KeyError(f"cliente falso não sabe os filhos de {bloco_id}")
        return tuple(self.filhos[bloco_id])

    def buscar_comentarios(self, bloco_id: str) -> tuple[dict[str, Any], ...] | None:
        valor = self.comentarios.get(bloco_id)
        return tuple(valor) if valor is not None else None


def test_item_numerado_preenchido_vira_frase_com_identidade_do_bloco_raiz() -> None:
    cliente = ClienteFalso({PAGINA: [_numerado("b1", "Feito é melhor que perfeito.")]})

    colecao = LeitorDeColecao(cliente).ler(PAGINA)

    assert len(colecao.itens) == 1
    assert colecao.itens[0].identidade == "b1"
    assert colecao.itens[0].blocos[0].trechos[0].texto == "Feito é melhor que perfeito."


def test_item_vazio_nao_vira_frase() -> None:
    # AC10: itens vazios não viram frases — e não é diagnóstico, é esperado.
    cliente = ClienteFalso({PAGINA: [_numerado("b1", "")]})

    colecao = LeitorDeColecao(cliente).ler(PAGINA)

    assert colecao.itens == ()
    assert colecao.diagnosticos == ()


def test_subpagina_e_ignorada_mesmo_sendo_o_projeto_inteiro() -> None:
    cliente = ClienteFalso({PAGINA: [_subpagina("projeto"), _numerado("b1", "uma frase")]})

    colecao = LeitorDeColecao(cliente).ler(PAGINA)

    assert [f.identidade for f in colecao.itens] == ["b1"]
    assert cliente.chamadas_de_filhos == [PAGINA]  # nunca desceu na subpágina


def test_conteudo_solto_no_nivel_da_colecao_gera_diagnostico() -> None:
    cliente = ClienteFalso({PAGINA: [_paragrafo("solto", "nota perdida entre os itens")]})

    colecao = LeitorDeColecao(cliente).ler(PAGINA)

    assert colecao.itens == ()
    assert len(colecao.diagnosticos) == 1
    assert colecao.diagnosticos[0].categoria == "conteudo_solto"
    assert "solto" in colecao.diagnosticos[0].descricao


def test_descendentes_entram_na_mesma_frase_em_ordem() -> None:
    cliente = ClienteFalso(
        {
            PAGINA: [_numerado("b1", "primeira linha", tem_filhos=True)],
            "b1": [_paragrafo("d1", "segunda linha"), _paragrafo("d2", "terceira linha")],
        }
    )

    colecao = LeitorDeColecao(cliente).ler(PAGINA)

    textos = [t.texto for bloco in colecao.itens[0].blocos for t in bloco.trechos]
    assert textos == ["primeira linha", "segunda linha", "terceira linha"]


def test_lista_numerada_interna_nao_cria_frase_independente() -> None:
    cliente = ClienteFalso(
        {
            PAGINA: [_numerado("b1", "item de topo", tem_filhos=True)],
            "b1": [_numerado("aninhado", "sublista, não é frase")],
        }
    )

    colecao = LeitorDeColecao(cliente).ler(PAGINA)

    assert len(colecao.itens) == 1
    assert colecao.itens[0].identidade == "b1"


def test_descendente_com_filhos_e_percorrido_recursivamente() -> None:
    cliente = ClienteFalso(
        {
            PAGINA: [_numerado("b1", "topo", tem_filhos=True)],
            "b1": [_paragrafo("d1", "nível 1", tem_filhos=True)],
            "d1": [_paragrafo("d2", "nível 2")],
        }
    )

    colecao = LeitorDeColecao(cliente).ler(PAGINA)

    textos = [t.texto for bloco in colecao.itens[0].blocos for t in bloco.trechos]
    assert textos == ["topo", "nível 1", "nível 2"]


def test_discussoes_do_bloco_raiz_entram_na_frase() -> None:
    cliente = ClienteFalso(
        filhos={PAGINA: [_numerado("b1", "com discussão")]},
        comentarios={"b1": [{"rich_text": _rich_text("um comentário")}]},
    )

    colecao = LeitorDeColecao(cliente).ler(PAGINA)

    assert colecao.itens[0].discussoes == ("um comentário",)


def test_acesso_negado_a_discussoes_vira_diagnostico_sem_falhar() -> None:
    cliente = ClienteFalso(
        filhos={PAGINA: [_numerado("b1", "sem acesso a discussão")]},
        comentarios={"b1": None},
    )

    colecao = LeitorDeColecao(cliente).ler(PAGINA)

    assert colecao.itens[0].discussoes == ()
    assert any(d.categoria == "acesso_negado" for d in colecao.diagnosticos)


def test_colecao_totalmente_vazia_e_um_snapshot_legitimo() -> None:
    cliente = ClienteFalso({PAGINA: []})

    colecao = LeitorDeColecao(cliente).ler(PAGINA)

    assert colecao.itens == ()
    assert colecao.diagnosticos == ()


def test_erro_ao_buscar_o_nivel_da_colecao_vira_sincronizacao_incompleta() -> None:
    class ClienteQuebrado:
        def buscar_filhos(self, bloco_id: str) -> tuple[dict[str, Any], ...]:
            raise ErroDoNotion("Notion respondeu HTTP 504")

        def buscar_comentarios(self, bloco_id: str) -> tuple[dict[str, Any], ...] | None:
            return ()

    with pytest.raises(SincronizacaoIncompleta):
        LeitorDeColecao(ClienteQuebrado()).ler(PAGINA)


def test_erro_ao_buscar_discussoes_tambem_vira_sincronizacao_incompleta() -> None:
    # Só acesso negado (403) vira diagnóstico; qualquer outro erro do Notion ao
    # buscar discussões precisa do mesmo tratamento dos outros dois pontos de
    # leitura — nunca escapar como ErroDoNotion cru (achado do code-review).
    class ClienteComDiscussaoQuebrada:
        def buscar_filhos(self, bloco_id: str) -> tuple[dict[str, Any], ...]:
            if bloco_id == PAGINA:
                return (_numerado("b1", "com discussão quebrada"),)
            raise AssertionError("não deveria buscar filhos de outro bloco")

        def buscar_comentarios(self, bloco_id: str) -> tuple[dict[str, Any], ...] | None:
            raise ErroDoNotion("Notion respondeu HTTP 500")

    with pytest.raises(SincronizacaoIncompleta):
        LeitorDeColecao(ClienteComDiscussaoQuebrada()).ler(PAGINA)


def test_erro_ao_buscar_descendentes_tambem_vira_sincronizacao_incompleta() -> None:
    # Uma frase com descendentes ilegíveis não pode virar uma frase truncada
    # silenciosamente: a leitura inteira precisa ser tratada como incompleta.
    class ClienteParcial:
        def buscar_filhos(self, bloco_id: str) -> tuple[dict[str, Any], ...]:
            if bloco_id == PAGINA:
                return (_numerado("b1", "topo", tem_filhos=True),)
            raise ErroDoNotion("Notion respondeu HTTP 504")

        def buscar_comentarios(self, bloco_id: str) -> tuple[dict[str, Any], ...] | None:
            return ()

    with pytest.raises(SincronizacaoIncompleta):
        LeitorDeColecao(ClienteParcial()).ler(PAGINA)
