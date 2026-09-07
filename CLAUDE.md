# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Estado do repositório

Ticket 02 concluído: existe esqueleto Python com testes e análise estática passando, e `GET /health` local. Nenhum comportamento de produto foi implementado ainda — sem Notion, sem Telegram, sem persistência, sem AWS.

**Leia a spec antes de escrever qualquer código.** Ela é a fonte de verdade do escopo, do vocabulário de domínio e dos 31 critérios de aceite (AC01–AC31). Precedência declarada na própria spec: refino aprovado > `Refino-inicial.txt` > página original do Notion.

## Comandos

Gerenciador: **uv** (o Python 3.13 é provisionado por ele; não use `pip` nem venv manual). Toda invocação passa por `uv run`.

```sh
make instalar     # uv sync — instala as dependências travadas no uv.lock
make teste        # uv run pytest — suíte completa
make lint         # ruff check + ruff format --check + mypy estrito
make verificar    # lint + teste; é o que o CI vai exigir
make formatar     # corrige o corrigível (ruff --fix e format)
```

Um único teste: `uv run pytest tests/dominio/test_tempo.py::test_fuso_local_e_sao_paulo`

Não há passo de build separado ainda — ele nasce com o empacotamento SAM no ticket 03.

`tests/test_arquitetura.py` falha se `dominio` ou `aplicacao` importarem `fastapi`, `mangum`, `starlette`, `boto3` ou `botocore`. Se precisar de uma dessas numa camada pura, o desenho está errado, não o teste.

## O que o sistema faz

Bot pessoal de usuária única que envia uma frase por dia às 08:00 (America/Sao_Paulo, inclusive fins de semana) no Telegram, lendo a coleção diretamente do Notion. Comandos: `/frase` (frase extra), `/status` (diagnóstico operacional), `/start` (ajuda). Roda inteiramente na AWS — o computador da usuária não participa da operação.

## Stack aprovada

Python, FastAPI, Mangum, AWS SAM, Lambda, EventBridge Scheduler, DynamoDB, S3 (cache de mídia), GitHub Actions. Substituições fora de escopo: JSON local, SQLite, PostgreSQL, APScheduler, TypeScript, Docker, servidor sempre ligado.

## Arquitetura — responsabilidades dos módulos

- **Domínio** — seleção, ciclos, elegibilidade, janela de envio, estados de entrega.
- **Aplicação** — coordena sincronização, reserva, tentativa, confirmação e status.
- **Notion** — busca blocos e converte em representação preservável.
- **Telegram** — valida entrada e envia partes de texto ou mídia.
- **Persistência** — snapshots, ciclos, pedidos, tentativas, controle de concorrência.
- **Infraestrutura** — recursos, permissões, agendamento, entrada HTTP, retenção.
- **Publicação** — PR, verificações, artefatos, promoção, recuperação.

Duas entradas separadas: HTTP (webhook via API Gateway → FastAPI → Mangum) e trabalho agendado (Scheduler chama os casos de uso diretamente). Um worker processa pedidos **persistidos** — nada de background tasks após retornar a resposta HTTP.

**Relógio, gerador aleatório e integrações devem ser substituíveis nos testes.** Os casos de uso não podem depender de FastAPI nem dos formatos de evento AWS.

## Vocabulário (use estes termos em código, testes e commits)

- **Frase** — item numerado preenchido e seu conteúdo descendente.
- **Coleção válida** — snapshot completo e validado da fonte, inclusive um snapshot legitimamente vazio.
- **Ciclo** — conjunto de frases consumidas desde o último reinício da seleção.
- **Pedido de envio** — solicitação diária ou `/frase`, com identidade persistente.
- **Tentativa** — execução de um pedido; várias tentativas pertencem ao mesmo pedido.
- **Entrega confirmada** — Telegram retornou sucesso *e* a aplicação persistiu a confirmação.
- **Entrega incerta** — a chamada pode ter produzido mensagem, mas não há confirmação durável.
- **Versão estável** — publicação verificada e aceita por merge; **versão candidata** — publicação de um PR ainda aberto.

## Invariantes que não são óbvias no código

Estas regras são a razão de a spec existir; violá-las quebra o produto de formas silenciosas.

**Sincronização do Notion**
- Identidade estável da frase é o **id do bloco raiz**, não o texto. Igualdade de texto nunca é critério de deduplicação.
- Um novo snapshot só é publicado **após leitura completa e validada**. Resposta parcial, timeout ou erro de autorização jamais podem ser interpretados como exclusão em massa.
- Leitura completa sem frases → snapshot vazio legítimo (não ressuscitar excluídos). Notion indisponível → manter a última coleção válida e marcar uso de cache.
- Autoria misturada ao texto é preservada **literalmente**; nunca separar por heurística nem inventar atribuição. Nenhuma chamada de IA participa da operação do bot.

**Seleção e ciclos**
- Sorteio sem repetição dentro do ciclo. Novas identidades entram no ciclo atual; edições não apagam a marca de consumo; exclusões removem elegibilidade preservando o histórico.
- Na virada de ciclo com ≥2 frases ativas, a última entregue fica fora das candidatas à primeira seleção.
- Diárias e extras compartilham o mesmo estado de ciclo. Uma nova tentativa **reutiliza a reserva existente**, não sorteia outra frase.
- Consumo só após entrega completa confirmada. Falha comprovada sem envio libera a reserva; entrega parcial ou incerta **mantém** a frase consumida com ressalva.

**Janela e agendamento**
- Alvo 08:00–08:15 local; janela de recuperação encerra às 12:00 do mesmo dia local. Instantes gravados em UTC; a chave diária é calculada pelo **dia local**.
- Persistir o próximo instante de tentativa — nunca manter Lambda dormindo. Checar a janela imediatamente antes de cada chamada ao Telegram.
- Um reconciliador periódico (proposta: 5 min) recupera pendentes e pode criar a diária ausente dentro da janela; a chave diária torna as duas entradas idempotentes.

**Idempotência**
- Diária = conversa autorizada + data local · Extra = bot + `update_id` · Parte = pedido + índice · Tentativa = pedido + sequencial.
- Reserva de pedido e de frase usam escritas condicionais e transações; ciclo e sequência de envio protegidos por **lease com prazo + token de versão**, para que um executor antigo não confirme nem avance uma reserva já transferida.
- Banco e chamada ao Telegram não estão na mesma transação. A spec **não promete** entrega exatamente uma vez sob falha ambígua: registrar intenção por parte antes do envio e, em resultado ambíguo, marcar *incerto* e **suspender reenvio automático** dessa parte.
- Estados terminais não são reabertos por evento duplicado.

**Fronteira HTTP**
- Webhook valida `X-Telegram-Bot-Api-Secret-Token`, tipo `private` e `chat_id` autorizado — `/status` também passa pela autenticação. Conversa não autorizada não recebe resposta e não gera pedido.
- O comando é **persistido antes** de confirmar recebimento. Falha ao persistir retorna erro para o Telegram reentregar. Webhook repetido retorna sucesso reconhecendo o registro existente.

**Persistência**
- Conteúdo extenso e históricos vão em itens separados — nenhum item com crescimento ilimitado. Deve haver índice de pendências que permita buscar trabalho vencido sem varrer o histórico.
- O conteúdo **efetivamente enviado** é preservado no histórico mesmo se a origem mudar. Dados e histórico não expiram; logs técnicos podem (proposta: 14 dias) e não substituem o histórico.
- Recursos duráveis de dados ficam separados dos recursos de aplicação, com proteção contra exclusão — atualização e recuperação não podem apagar histórico. Migrações destrutivas estão fora do MVP; mudanças de dados são aditivas e legíveis pela versão anterior.

## CI/CD — ordem obrigatória

Único ambiente de produção. `develop` e `main` permanentes; **merge sempre manual**; publicação acontece a partir de `develop`, **antes** do merge.

1. Capturar SHA imutável do push e localizar o PR.
2. Testes, análise estática, validação SAM.
3. Build **uma vez**, artefato identificado por SHA + checksum.
4. Entrar na exclusão mútua de produção; reconsultar PR aberto e SHA atual.
5. Registrar publicação em andamento e invalidar a candidata anterior.
6. Publicar exatamente o artefato avaliado.
7. Verificar saúde, versão ativa, dependências, webhook e agendamento — sem consumir frase nem enviar mensagem de teste.
8. Registrar sucesso apenas no SHA publicado e ainda atual no PR.
9. Liberar merge manual com os checks aprovados.

Publicação e recuperação compartilham o mesmo grupo de exclusão mútua e **verificam atualidade após esperar** — não presumir ordem FIFO dos jobs. Apenas jobs sem mutação podem ser cancelados livremente. Um evento antigo nunca sobrescreve uma publicação posterior; repetir um evento de recuperação é idempotente.

Recuperação por caso: falha de deploy ou de diagnóstico → publicação saudável anterior à tentativa; PR fechado sem merge → versão estável anterior ao PR (não uma candidata do mesmo PR); primeiro deploy sem versão anterior → reverter o possível, **desabilitar envios** e documentar o estado.

OIDC precisa existir **antes** do primeiro pipeline com acesso AWS — um pipeline sem confiança não cria a própria autorização. Papéis de publicação e de infraestrutura são separados; `id-token: write` só no job que assume papel AWS.

## Testes

Fronteira principal: casos de uso públicos de **enviar frase** e **consultar status**, com relógio, sorteio, Notion, Telegram e persistência controláveis. Verificar mensagens produzidas, estado observável e histórico — não testar métodos privados nem espelhar a implementação. Complementar com testes de contrato nas fronteiras HTTP/integração e testes de concorrência do repositório DynamoDB (atomicidade, retomada, corrida). CI usa fixtures e integrações simuladas.

Cada mudança deve mapear para um AC da seção 5 da spec. O aceite AWS (entrega real, `/frase`, `/status`, persistência entre versões, recuperação exercitada) é manual e não roda a cada commit.

## Restrições de projeto

- Meta de custo recorrente **R$0**, sem promessa de gratuidade — verificar franquias, minutos de Actions e armazenamento antes de provisionar; evitar VPC/NAT sem necessidade demonstrada. A varredura periódica entra na estimativa.
- Segredos (token Notion, token Telegram, `chat_id`, segredo do webhook) ficam fora do Git; parâmetros de infraestrutura não aparecem em logs. Sanitizar tokens, URLs assinadas e conteúdo pessoal dos logs.
- Dedicação da usuária é **< 2 horas semanais**: entregar em sessões pequenas, cada uma explicando o comportamento implementado, a decisão técnica, o que os testes demonstram e o próximo passo.
- Fora de escopo (seção 6 da spec): múltiplos usuários, dashboard, IA na operação, filtros/favoritas, cards gerados, armazenamento local em produção, ambiente AWS de dev, merge automático, exclusão de mensagens já enviadas.

## Decisões confirmadas pela usuária (2026-09-06)

Já fechadas — implemente conforme descrito, não reabra:
- **Janela dos extras:** `/frase` antes das 12:00 pode retentar até as 12:00; a partir das 12:00, tentativa única imediata e, falhando, encerra com diagnóstico. Sem fila para o dia seguinte.
- **Entrega incerta:** tratamento conservador — marcar a parte como incerta e suspender o reenvio automático, aceitando o risco de uma mensagem perdida em troca de não duplicar.

## Decisões ainda em aberto

Não feche estes pontos sem confirmação da usuária:
- Recursos auxiliares propostos, não aprovados no refino: HTTP API, cache S3, armazenamento de segredos.
- Rastreador de issues e vocabulário de triagem não configurados; `ready-for-agent` é triagem sugerida, não label aplicada.

## Tickets

O trabalho está quebrado em 22 tickets em `.scratch/frase-diaria-telegram/issues/`, numerados em ordem de dependência (bloqueadores primeiro). Cada arquivo declara seu **Blocked by**. Trabalhe a fronteira: qualquer ticket cujos bloqueadores estejam prontos. Os tickets 01 e 02 não têm bloqueadores.
