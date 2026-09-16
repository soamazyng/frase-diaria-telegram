from dataclasses import dataclass

from frase_diaria.dominio.autorizacao import Conversa
from frase_diaria.dominio.comando import Comando


@dataclass(frozen=True)
class Atualizacao:
    """Comando externo já reduzido ao vocabulário do domínio."""

    update_id: int
    conversa: Conversa
    comando: Comando
