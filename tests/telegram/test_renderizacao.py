from frase_diaria.dominio.colecao import FrasePreservada
from frase_diaria.dominio.conteudo import Bloco, Trecho
from frase_diaria.telegram.renderizacao import RenderizadorTelegram


def _frase(*trechos: Trecho) -> FrasePreservada:
    return FrasePreservada(
        identidade="bloco-1",
        blocos=(Bloco(tipo="paragraph", trechos=trechos),),
    )


def test_renderiza_anotacoes_escape_e_link_em_html_do_telegram() -> None:
    frase = _frase(
        Trecho(texto="<forte>", negrito=True),
        Trecho(texto=" e código", codigo=True),
        Trecho(texto=" link", link="https://example.test/a?x=1&y=2"),
    )

    resultado = RenderizadorTelegram().renderizar(frase)

    assert resultado is not None
    assert resultado.partes == (
        "<b>&lt;forte&gt;</b><code> e código</code>"
        '<a href="https://example.test/a?x=1&amp;y=2"> link</a>',
    )


def test_renderiza_blocos_em_ordem_com_quebra_de_linha() -> None:
    frase = FrasePreservada(
        identidade="bloco-1",
        blocos=(
            Bloco(tipo="paragraph", trechos=(Trecho(texto="primeiro"),)),
            Bloco(tipo="quote", trechos=(Trecho(texto="segundo", italico=True),)),
        ),
    )

    resultado = RenderizadorTelegram().renderizar(frase)

    assert resultado is not None
    assert resultado.partes == ("primeiro\n<i>segundo</i>",)


def test_cor_sem_equivalente_visual_vira_negrito() -> None:
    resultado = RenderizadorTelegram().renderizar(_frase(Trecho(texto="destaque", cor="red")))

    assert resultado is not None
    assert resultado.partes == ("<b>destaque</b>",)


def test_divide_texto_no_limite_sem_perder_conteudo_ou_marcas() -> None:
    frase = _frase(Trecho(texto="abcdefghij", negrito=True))

    resultado = RenderizadorTelegram(limite_de_texto=4).renderizar(frase)

    assert resultado is not None
    assert resultado.partes == ("<b>abcd</b>", "<b>efgh</b>", "<b>ij</b>")


def test_conteudo_sem_texto_nao_vira_frase() -> None:
    frase = FrasePreservada(identidade="imagem", blocos=(Bloco(tipo="image"),))

    assert RenderizadorTelegram().renderizar(frase) is None
