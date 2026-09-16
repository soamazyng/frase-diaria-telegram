# 26 — Status por destinatário

## Comportamento

`/status` resolve a diária e o último envio a partir das confirmações e incertezas
de quem consultou (AC35/AC36). Quem recebeu todas as partes vê `enviada`, mesmo
quando outra conversa falhou ou aguarda retentativa. Uma falha definitiva própria
aparece como `falhou` ou `parcial`, conforme as partes confirmadas. A próxima
ocorrência usa esse desfecho individual e continua no fuso de São Paulo (AC17).

A consulta não sincroniza, reserva nem consome frases. Pedidos dos quais a conversa
não participou não entram no relatório. Motivos compartilhados viram categorias
seguras; motivos individuais passam pela lista permitida de diagnóstico.

## Decisão técnica e persistência

O worker grava `total_de_partes` antes de enviar e registra
`destinatarios_com_falha` quando uma entrega termina com falha definitiva. Esses
campos permitem distinguir confirmação completa, parcial e falha sem consultar o
Notion. Ambos são aditivos e usam as escritas do pedido protegidas pelo lease.
Uma intenção abandonada é registrada como incerta durante a retomada, sem reenviar.

Padrões de acesso permanecem: obter a diária de hoje/ontem por chave, consultar
partes pelo pedido e destinatário, e atualizar o pedido pelo dono do lease. Não há
Scan, índice, tabela, serviço ou permissão novos. A fronteira de autorização é a
conversa validada no webhook; a consulta ainda verifica pertencimento ao pedido.
Dados e histórico conservam retenção e proteções existentes.

O total ocupa espaço constante; a lista de falhas é limitada aos destinatários do
pedido. Há uma escrita adicional no primeiro registro de falha definitiva por destinatário
e uma transação na conversão de intenção em incerteza. O volume permanece proporcional ao pequeno conjunto familiar. Não foi
feita nova cotação nem benchmark AWS; a estimativa-base permanece em
`docs/01-custo-e-elegibilidade.md`, sem provisionamento nesta task.

Pedidos sem campos novos continuam legíveis. No histórico individual, o estado do
pedido já é o estado da própria conversa. Em pedidos compartilhados encerrados
antes deste ticket, sem total persistido, confirmações parciais não permitem provar
que todas as partes chegaram; esse histórico conserva a classificação conservadora
`parcial`. Não há migração ou reconstrução a partir do conteúdo atual do Notion.
O alcance preexistente de “último envio” continua limitado às diárias de hoje e ontem.

## Skills e verificação

O registro da implementação anterior cita `implement`, `python-clean-code`, `tdd`,
`python-testing-patterns`, `amazon-dynamodb` e `code-review`. Nesta conclusão foram
reaplicadas `implement`, `python-clean-code`, `tdd`, `python-testing-patterns` e
`code-review`. Fronteiras: `ProcessarPedido.executar`,
`ConsultarStatus.executar`, `EnviarStatus.executar` e contrato público do repositório.
Ao retomar a task havia sete arquivos de código/testes modificados e este documento
novo. O trabalho da task foi preservado e concluído; uma cópia inicial foi guardada
fora do repositório antes das edições. Alterações alheias em skills ficaram fora do commit.

Clean Code: nomes do domínio e efeitos explícitos (N1/G20), regras separadas do I/O
(G30), constantes compartilhadas (G5/G25), comentários de restrições em vez de
histórico de revisão (C1/C3), tipos nas interfaces (P3). Assinaturas existentes com
mais de três argumentos são mantidas para preservar os contratos; testes com Moto
não se limitam a 100 ms porque verificam persistência realista. `uv`/Makefile
prevalecem sobre os exemplos genéricos de instalação da skill.

Testes vermelho → verde observados: completo versus incerto; desfechos próprios
durante retentativa alheia; persistência do total e das falhas; isolamento de
conversas adicionadas depois; histórico individual legado; sanitização do motivo.
O teste de lease recusa a alteração dos metadados por um executor superado.
As fixtures dos dois arquivos de aplicação usam identificadores fictícios.

Durante a implementação, a suíte focal detectou uma tentativa indevida de repetir
a transição para `ENVIANDO` ao adicionar metadados a um pedido já em envio; corrigida
antes do gate final. Os testes não acessam AWS, Notion ou Telegram reais.

A revisão inicial encontrou dois impedimentos, ambos reproduzidos antes da correção:

- Standards: a conversão de intenção podia sobrescrever uma confirmação após perder
  o lease. Agora usa transação com condição no dono do pedido e no estado da parte;
  atualiza os atributos de diagnóstico preservando texto e identidade. Os testes
  intercalam transferência de lease e confirmação, recusando a escrita antiga.
- Spec: uma falha definitiva virava incerteza na retentativa causada por outro
  destinatário. Agora o worker preserva o desfecho definitivo e não revisita sua
  intenção. Testes de duas execuções cobrem falha sem envio e entrega parcial.

Conclusão em 2026-09-16: `make verificar` passou após as últimas correções
(Ruff, formatação, mypy em 83 arquivos e **433 testes**). A suíte focal inicial
passou com 131 testes. Há 366 avisos de depreciação em Starlette/Botocore, sem falhas.
A primeira execução do gate encontrou uma linha acima do limite em `pedidos.py`;
a formatação foi corrigida antes da validação final.

A revisão final usou como base `3395609` e somente os arquivos da task, com agentes
independentes de Standards e Spec. Ambos encontraram uma lacuna adicional: uma
retomada com parte incerta podia liberar a frase após falha permanente de outra
parte ou encerramento da janela. O teste público parametrizado reproduziu os dois
defeitos antes da correção. Os dois encerramentos agora consultam a incerteza
persistida e conservam o consumo com ressalva (spec 4.4, AC15/AC16).

Também foi exercitada uma mutação apenas em memória que fazia o status usar o
agregado: o teste de destinatários com resultados diferentes falhou como esperado
e passou novamente sem a mutação. Nenhuma mutação permaneceu no código.

**Standards: OK. Spec: OK.** Reavaliação dos trechos corrigidos sem achados
pendentes. O histórico anterior de correções acima foi preservado; os resultados
deste fechamento foram executados novamente nesta sessão. O rastreador usado foi
a issue local, pois `docs/agents/issue-tracker.md` não existe; configurar
`/setup-matt-pocock-skills` é uma pendência administrativa independente.

Não houve alteração de templates SAM, IAM ou serviços; validação SAM e aceite real
AWS/Telegram/Notion não foram executados nesta task. O aceite real pertence ao ticket 27.

## Revisão adicional de `processar_pedido.py`

A usuária solicitou explicitamente uma revisão e correção do arquivo com
`python-clean-code` durante a conclusão desta task. Aplicadas:

- G30/G34: separação entre percorrer destinatários, entregar uma parte, registrar
  incerteza e classificar falha transitória/permanente.
- G5/F1/P3: contexto imutável da tentativa agrupa pedido, destinatário e sequencial;
  os dois caminhos de incerteza usam a mesma persistência tipada.
- G2/G4: removidos `getattr` com fallback que podiam omitir intenção ou incerteza
  silenciosamente, apesar de serem operações obrigatórias do contrato.
- N1/C1/C3/G25: nomes locais claros, comentários operacionais e constante para a
  proporção de dispersão no backoff.
- G3/T5: corrigido o limite inclusivo do prazo (AC14); nenhum novo envio no instante
  limite. O teste falhou antes da correção.
- G2/G4/T6: uma incerteza persistida não vira sucesso na retomada; entrega incerta
  mantém consumo com ressalva mesmo sem parte confirmada (AC15/AC16 e spec 4.4).
  Os testes reproduziram os dois defeitos antes da correção.

As assinaturas de portas e os fluxos de reserva/ciclo existentes foram preservados,
exceto pelo sequencial obrigatório na gravação de incerteza, necessário para validar
o lease. Flags existentes que descrevem o resultado persistido do ciclo permanecem;
não foram criados wrappers apenas para cumprir limites numéricos da skill.

## Próximo passo

Ticket 27: aceite real com o destinatário adicional, cadastro seguro de configuração
e validação de diária, `/frase` e `/status`. Esta task não publica, não altera SSM e
não envia mensagens reais; o aceite em produção continua pendente.
