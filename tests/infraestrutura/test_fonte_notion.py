"""Adapta a sincronização (com cache) à porta FonteDeFrases do worker.

A conversão de conteúdo preservado para texto plano aqui é um placeholder até
o ticket 12 (renderização rica e divisão de mensagens): só concatena o texto
literal dos trechos, sem formatação nem divisão inteligente.
"""

from datetime import UTC, datetime

from frase_diaria.aplicacao.sincronizar_colecao import ResultadoDaSincronizacao
from frase_diaria.dominio.colecao import ColecaoValida, FrasePreservada
from frase_diaria.dominio.conteudo import Bloco, Trecho
from frase_diaria.infraestrutura.fonte_notion import FonteDeFrasesNotion


class SincronizarFalso:
    def __init__(self, resultado: ResultadoDaSincronizacao) -> None:
        self.resultado = resultado
        self.chamadas = 0

    def executar(self) -> ResultadoDaSincronizacao:
        self.chamadas += 1
        return self.resultado


def _resultado(itens: tuple[FrasePreservada, ...]) -> ResultadoDaSincronizacao:
    return ResultadoDaSincronizacao(
        colecao=ColecaoValida(itens=itens),
        usou_cache=False,
        instante_do_snapshot=datetime(2026, 9, 7, 8, 0, tzinfo=UTC),
    )


def test_lista_converte_cada_frase_preservada_em_frase_entregavel() -> None:
    preservada = FrasePreservada(
        identidade="b1",
        blocos=(Bloco(tipo="numbered_list_item", trechos=(Trecho(texto="conteúdo da frase"),)),),
    )
    fonte = FonteDeFrasesNotion(sincronizar=SincronizarFalso(_resultado((preservada,))))

    frases = fonte.listar()

    assert len(frases) == 1
    assert frases[0].identidade == "b1"
    assert frases[0].partes == ("conteúdo da frase",)


def test_concatena_trechos_do_mesmo_bloco_e_junta_blocos_em_linhas() -> None:
    preservada = FrasePreservada(
        identidade="b1",
        blocos=(
            Bloco(
                tipo="numbered_list_item",
                trechos=(Trecho(texto="primeira "), Trecho(texto="linha")),
            ),
            Bloco(tipo="paragraph", trechos=(Trecho(texto="segunda linha"),)),
        ),
    )
    fonte = FonteDeFrasesNotion(sincronizar=SincronizarFalso(_resultado((preservada,))))

    frases = fonte.listar()

    assert frases[0].partes == ("primeira linha\nsegunda linha",)


def test_bloco_sem_trechos_e_ignorado_na_concatenacao() -> None:
    # Um bloco de imagem, por exemplo, não tem rich text (cache de mídia é do
    # ticket 13) — não pode virar uma linha vazia no meio do texto.
    preservada = FrasePreservada(
        identidade="b1",
        blocos=(
            Bloco(tipo="numbered_list_item", trechos=(Trecho(texto="texto"),)),
            Bloco(tipo="image"),
        ),
    )
    fonte = FonteDeFrasesNotion(sincronizar=SincronizarFalso(_resultado((preservada,))))

    frases = fonte.listar()

    assert frases[0].partes == ("texto",)


def test_frase_sem_nenhum_trecho_e_ignorada_em_vez_de_derrubar_a_listagem() -> None:
    # Regressão (achado do code-review): se todo bloco de uma frase ficar sem
    # rich text, gerar uma parte vazia levantaria ValueError em Frase() e
    # quebraria a entrega de TODAS as frases, não só dessa — não de uma.
    sem_texto = FrasePreservada(identidade="b1", blocos=(Bloco(tipo="image"),))
    com_texto = FrasePreservada(
        identidade="b2", blocos=(Bloco(tipo="numbered_list_item", trechos=(Trecho(texto="ok"),)),)
    )
    fonte = FonteDeFrasesNotion(sincronizar=SincronizarFalso(_resultado((sem_texto, com_texto))))

    frases = fonte.listar()

    assert [f.identidade for f in frases] == ["b2"]


def test_colecao_vazia_devolve_nenhuma_frase() -> None:
    fonte = FonteDeFrasesNotion(sincronizar=SincronizarFalso(_resultado(())))

    assert fonte.listar() == ()
