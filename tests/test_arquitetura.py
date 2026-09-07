"""O domínio e a aplicação não podem depender de FastAPI nem de formatos de evento AWS.

Esta é uma invariante da spec (seção 4.1): os casos de uso precisam ser exercitáveis
sem web framework e sem envelope de Lambda. Um teste guarda a regra melhor que um
comentário, porque quebra no CI quando alguém importa o que não deve.
"""

import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent / "src" / "frase_diaria"
CAMADAS_PURAS = ("dominio", "aplicacao")
DEPENDENCIAS_PROIBIDAS = ("fastapi", "mangum", "starlette", "boto3", "botocore")


def _modulos_das_camadas_puras() -> list[Path]:
    return sorted(caminho for camada in CAMADAS_PURAS for caminho in (RAIZ / camada).rglob("*.py"))


def _nomes_importados(arquivo: Path) -> set[str]:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.update(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            nomes.add(no.module)
    return nomes


def test_existem_modulos_para_inspecionar() -> None:
    assert _modulos_das_camadas_puras(), "nenhum módulo encontrado nas camadas puras"


@pytest.mark.parametrize("arquivo", _modulos_das_camadas_puras(), ids=lambda p: p.name)
def test_camada_pura_nao_importa_framework_web_nem_sdk_aws(arquivo: Path) -> None:
    raizes = {nome.split(".")[0] for nome in _nomes_importados(arquivo)}
    proibidas_encontradas = raizes.intersection(DEPENDENCIAS_PROIBIDAS)

    assert not proibidas_encontradas, (
        f"{arquivo.relative_to(RAIZ)} importa {sorted(proibidas_encontradas)}; "
        "domínio e aplicação devem permanecer independentes de FastAPI e da AWS"
    )
