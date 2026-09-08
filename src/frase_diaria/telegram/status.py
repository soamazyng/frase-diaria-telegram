"""Formata o relatório de `/status` em texto para a Bot API.

Converte todo instante para o fuso local só nesta camada — o relatório em si
(`dominio/status.py`) guarda tudo em UTC. `parse_mode=HTML` é sempre enviado
(`telegram/canal.py`), então qualquer texto dinâmico (motivo, erro) precisa de
escape: sem isso um "<" ou "&" do lado do Telegram/Notion quebraria a mensagem.
"""

from datetime import datetime
from html import escape

from frase_diaria.dominio.pedido import MOTIVO_PADRAO, EstadoDoPedido
from frase_diaria.dominio.status import RelatorioDeStatus
from frase_diaria.dominio.tempo import FUSO_LOCAL

_ROTULO_DO_ESTADO = {
    EstadoDoPedido.PENDENTE: "pendente",
    EstadoDoPedido.RESERVADO: "reservada",
    EstadoDoPedido.ENVIANDO: "enviando",
    EstadoDoPedido.AGUARDANDO_TENTATIVA: "aguardando nova tentativa",
    EstadoDoPedido.ENVIADO: "enviada",
    EstadoDoPedido.PARCIAL: "parcial",
    EstadoDoPedido.INCERTO: "incerta",
    EstadoDoPedido.FALHOU: "falhou",
    EstadoDoPedido.EXPIRADO: "expirada",
}


def _local(instante: datetime | None) -> str:
    return instante.astimezone(FUSO_LOCAL).strftime("%d/%m %H:%M") if instante else "nunca"


def formatar_status(relatorio: RelatorioDeStatus) -> str:
    linhas: list[str] = []
    linhas.extend(_linhas_da_diaria(relatorio))
    linhas.extend(_linhas_do_ultimo_envio(relatorio))
    linhas.append(f"Próxima ocorrência diária: {_local(relatorio.proxima_ocorrencia_diaria)}")
    linhas.extend(_linhas_da_sincronizacao(relatorio))
    return "\n".join(linhas)


def _linhas_da_diaria(relatorio: RelatorioDeStatus) -> list[str]:
    situacao = relatorio.situacao_da_diaria_de_hoje
    if not situacao.existe:
        return ["Diária de hoje: ainda não criada."]

    assert situacao.estado is not None  # `existe` garante isto
    linha = f"Diária de hoje: {_ROTULO_DO_ESTADO[situacao.estado]}"
    if situacao.motivo and situacao.motivo != MOTIVO_PADRAO:
        linha += f" ({escape(situacao.motivo)})"
    linhas = [linha]
    if situacao.tem_partes_incertas:
        linhas.append(
            "Há parte(s) incerta(s) na diária de hoje: não serão reenviadas automaticamente."
        )
    return linhas


def _linhas_do_ultimo_envio(relatorio: RelatorioDeStatus) -> list[str]:
    ultimo = relatorio.ultimo_envio
    if ultimo is None:
        return ["Último envio: nunca."]
    # Sem "confirmado" no rótulo: um envio parcial ou incerto entra aqui (é o
    # mais recente que chegou à usuária), mas "confirmado" é vocabulário
    # reservado a entrega com sucesso e persistência da confirmação — dizê-lo
    # de um parcial/incerto seria impreciso (CLAUDE.md, vocabulário).
    rotulo = _ROTULO_DO_ESTADO[ultimo.estado]
    linhas = [f"Último envio: {ultimo.dia.strftime('%d/%m')} ({rotulo})"]
    if ultimo.tem_partes_incertas:
        linhas.append(
            "Esse envio inclui parte(s) incerta(s): não serão reenviadas automaticamente."
        )
    return linhas


def _linhas_da_sincronizacao(relatorio: RelatorioDeStatus) -> list[str]:
    sinc = relatorio.sincronizacao
    linhas = [f"Última tentativa de sincronização: {_local(sinc.instante_da_ultima_tentativa)}"]

    if not sinc.colecao_disponivel:
        motivo = escape(sinc.erro) if sinc.erro else "motivo desconhecido"
        linhas.append(f"Sincronização: sem coleção válida disponível ({motivo}).")
        return linhas

    origem = "cache" if sinc.usou_cache else "Notion"
    linhas.append(
        f"Última sincronização válida: {_local(sinc.instante_da_ultima_valida)} (via {origem})."
    )
    if sinc.erro:
        linhas.append(f"Falha ativa na sincronização: {escape(sinc.erro)}")
    return linhas
