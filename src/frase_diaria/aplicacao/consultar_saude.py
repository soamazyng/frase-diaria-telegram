from dataclasses import dataclass

from frase_diaria.aplicacao.portas import Relogio
from frase_diaria.dominio.saude import Saude


@dataclass(frozen=True)
class ConsultarSaude:
    """Responde se a aplicação está no ar e qual versão está ativa.

    A verificação pós-publicação usa este caso de uso: ele não consome frase nem
    envia mensagem de teste.
    """

    relogio: Relogio
    versao: str

    def executar(self) -> Saude:
        return Saude(versao=self.versao, instante=self.relogio.agora())
