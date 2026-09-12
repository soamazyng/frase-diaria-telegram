# frase-diaria-telegram

[![CI/CD develop -> main](https://github.com/soamazyng/frase-diaria-telegram/actions/workflows/pr-develop-main.yml/badge.svg?branch=develop)](https://github.com/soamazyng/frase-diaria-telegram/actions/workflows/pr-develop-main.yml)
[![Reconciliador de publicações](https://github.com/soamazyng/frase-diaria-telegram/actions/workflows/reconciliador.yml/badge.svg)](https://github.com/soamazyng/frase-diaria-telegram/actions/workflows/reconciliador.yml)
![Python](https://img.shields.io/badge/python-3.13-blue?logo=python&logoColor=white)
![AWS SAM](https://img.shields.io/badge/AWS-SAM%20%7C%20Lambda%20%7C%20DynamoDB-FF9900?logo=amazonaws&logoColor=white)
![Custo recorrente](https://img.shields.io/badge/custo%20recorrente-R%240-brightgreen)
![Status](https://img.shields.io/badge/MVP-concluído-success)
![Uso](https://img.shields.io/badge/uso-pessoal%20%2F%20privado-lightgrey)

Bot pessoal de usuária única que envia uma frase por dia às 08:00 (America/Sao_Paulo,
inclusive fins de semana) no Telegram, lendo a coleção diretamente do Notion. Roda
inteiramente na AWS — o computador da usuária não participa da operação — e cabe
inteiro na franquia *Always Free* da AWS mais o plano GitHub já existente.

Comandos do bot: `/frase` (frase extra, mesmo ciclo da diária), `/status` (diagnóstico
operacional completo, em horário local) e `/start` (ajuda).

## O que já funciona

Os 22 tickets do épico estão concluídos — entrega diária, extras, `/status`,
sincronização com o Notion (com cache e fallback), publicação serializada por SHA,
recuperação automática de falhas, reconciliador periódico e proteção de `main` com
merge manual. Falta só um item de tempo, não de implementação: a avaliação pessoal de
valor depois de duas semanas de uso (AC31).

## Arquitetura, em uma frase

Duas entradas — webhook do Telegram (API Gateway → FastAPI → Mangum) e agendamento
(EventBridge Scheduler → Lambda) — convergem nos mesmos casos de uso, que só
conhecem portas (`aplicacao/portas.py`), nunca framework ou SDK da AWS diretamente.
Estado durável vive em uma única tabela DynamoDB, protegida contra exclusão e
separada da stack de aplicação, de forma que republicar código nunca alcança os
dados.

| Pacote | Responsabilidade |
|---|---|
| `dominio` | Seleção, ciclos, elegibilidade, janela de envio, estados de entrega |
| `aplicacao` | Casos de uso e as portas que eles exigem |
| `notion` | Busca blocos e converte em representação preservável |
| `telegram` | Valida entrada e envia partes de texto ou mídia |
| `persistencia` | Snapshots, ciclos, pedidos, tentativas, concorrência |
| `infraestrutura` | Adaptadores concretos, configuração e entradas (HTTP e agendada) |

`dominio` e `aplicacao` não importam FastAPI, Mangum, boto3 nem botocore —
`tests/test_arquitetura.py` falha no CI se alguém quebrar essa regra.

## CI/CD

`develop` publica em produção a cada push, antes do merge para `main` — o merge é
sempre manual e só registra uma candidata já publicada e verificada como estável,
nunca dispara uma segunda publicação. Um reconciliador de hora em hora cobre o que
o pipeline síncrono não alcança (runner interrompido, PR fechado sem merge).
`main` é protegida de verdade contra push direto, exigindo os 5 checks obrigatórios.

## Documentação

- `contextIA/Spec-Frase-Diaria-Telegram.md` — especificação funcional aprovada,
  fonte de verdade do escopo e dos 31 critérios de aceite.
- `AGENTS.md` / `CLAUDE.md` — como trabalhar no projeto.
- `rules.md` — armadilhas operacionais já pagas, cada uma com o incidente que a
  originou.
- `docs/` — um documento por ticket, com decisão técnica, verificação real contra
  AWS/GitHub e o que ficou provado.
- `.scratch/frase-diaria-telegram/issues/` — os 22 tickets, numerados em ordem de
  dependência.

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
