"""O conteúdo preservado de uma frase é uma sequência ordenada de blocos.

Cada bloco guarda rich text literal — negrito, itálico, link — porque separar
autoria do texto por heurística inventaria atribuição (spec, 4.2). A
interpretação de como cada bloco vira mensagem do Telegram é do ticket 12;
aqui só interessa que nada se perca na leitura.
"""

from frase_diaria.dominio.conteudo import Bloco, Trecho


def test_trecho_simples_tem_apenas_texto() -> None:
    trecho = Trecho(texto="Feito é melhor que perfeito.")

    assert trecho.texto == "Feito é melhor que perfeito."
    assert not trecho.negrito
    assert trecho.link is None


def test_trecho_preserva_anotacoes_e_link() -> None:
    trecho = Trecho(texto="Sheryl Sandberg", negrito=True, link="https://exemplo.com/sheryl")

    assert trecho.negrito
    assert trecho.link == "https://exemplo.com/sheryl"


def test_bloco_preserva_o_tipo_bruto_e_a_ordem_dos_trechos() -> None:
    bloco = Bloco(
        tipo="paragraph",
        trechos=(Trecho(texto="parte um "), Trecho(texto="parte dois", italico=True)),
    )

    assert bloco.tipo == "paragraph"
    assert [t.texto for t in bloco.trechos] == ["parte um ", "parte dois"]


def test_bloco_pode_nao_ter_trechos() -> None:
    # Um bloco de imagem, por exemplo, não tem rich text — só referência de mídia
    # (cache de mídia é do ticket 13; aqui só não se quebra ao encontrar um).
    bloco = Bloco(tipo="image")

    assert bloco.trechos == ()
