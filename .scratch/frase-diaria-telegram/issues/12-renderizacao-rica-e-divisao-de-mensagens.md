# 12 — Renderização rica e divisão de mensagens

**What to build:** a frase chega no Telegram com a intenção visual do Notion preservada — negrito, itálico, código, links — e frases longas chegam inteiras, divididas em várias mensagens na ordem certa, sem marcação quebrada.

**Blocked by:** 10 — Sincronização com Notion substitui as fixtures.

**Status:** ready-for-agent

- [ ] Renderização em HTML suportado pela Bot API, com escape correto de caracteres.
- [ ] Negrito, itálico, código e links preservados; cores e fundos do Notion viram destaque em negrito quando não houver equivalente.
- [ ] Apenas metadados operacionais são removidos da mensagem; o conteúdo da usuária não é reescrito nem resumido.
- [ ] Texto longo é dividido sem perda, mantendo a ordem e marcação válida em cada parte (AC11).
- [ ] Acentos, caracteres especiais, links e destaques sobrevivem à renderização (AC11).
- [ ] Limites de texto e de legenda são validados contra os contratos atuais da Bot API, não contra números fixos presumidos.
- [ ] Uma frase permanece uma entrega lógica, ainda que ocupe várias mensagens.
