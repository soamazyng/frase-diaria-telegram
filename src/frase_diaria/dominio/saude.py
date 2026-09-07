from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Saude:
    """Diagnóstico mínimo da aplicação publicada.

    Carrega apenas o identificador da versão e o instante da consulta: nenhum dado
    pessoal e nenhum segredo atravessa esta fronteira.
    """

    versao: str
    instante: datetime
