# frase-diaria-telegram

Bot pessoal de usuária única que envia uma frase por dia às 08:00 (America/Sao_Paulo,
inclusive fins de semana) no Telegram, lendo a coleção diretamente do Notion.

Comandos do bot: `/frase` (frase extra), `/status` (diagnóstico), `/start` (ajuda).
Roda inteiramente na AWS — o computador da usuária não participa da operação.

A especificação funcional aprovada está em `contextIA/Spec-Frase-Diaria-Telegram.md`
e é a fonte de verdade do escopo. O trabalho está quebrado em tickets numerados em
`.scratch/frase-diaria-telegram/issues/`.

## Desenvolvimento

Requer [uv](https://docs.astral.sh/uv/). O Python 3.13 é provisionado pelo próprio uv.

```sh
make instalar     # instala as dependências travadas no uv.lock
make teste        # roda a suíte de testes
make lint         # ruff (regras + formatação) e mypy estrito
make verificar    # lint + teste, o que o CI vai exigir
```

Para rodar um único teste:

```sh
uv run pytest tests/dominio/test_tempo.py::test_fuso_local_e_sao_paulo
```

## Estrutura

| Pacote | Responsabilidade |
|---|---|
| `dominio` | Seleção, ciclos, elegibilidade, janela de envio, estados de entrega |
| `aplicacao` | Casos de uso e as portas que eles exigem |
| `notion` | Busca blocos e converte em representação preservável |
| `telegram` | Valida entrada e envia partes de texto ou mídia |
| `persistencia` | Snapshots, ciclos, pedidos, tentativas, concorrência |
| `infraestrutura` | Adaptadores concretos, configuração e entradas (HTTP e agendada) |

`dominio` e `aplicacao` não importam FastAPI nem SDK da AWS — `tests/test_arquitetura.py`
falha no CI se alguém quebrar essa regra.
