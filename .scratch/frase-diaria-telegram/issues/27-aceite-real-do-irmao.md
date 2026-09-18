# 27 — Aceite real com o irmão como destinatário

**What to build:** o irmão da usuária é cadastrado como destinatário de verdade, recebe
a diária real e usa `/frase` e `/status` na própria conta do Telegram — validação fora
de fixtures, no ambiente de produção único do projeto.

**Blocked by:** 24 — Autorização e comandos reconhecem múltiplos destinatários;
25 — Diária com múltiplos destinatários: entrega compartilhada e falhas independentes;
26 — `/status` reporta a entrega do próprio destinatário.

**Status:** concluído em 2026-09-16 — ver `docs/27-aceite-real-do-irmao.md`

- [x] Chat_id do irmão cadastrado no SSM pela usuária, fora da conversa com o agente
      (rules.md).
- [x] Irmão recebe a diária real, com o mesmo conteúdo entregue à usuária no mesmo dia.
- [x] Irmão usa `/frase` e recebe uma frase extra própria.
- [x] Irmão usa `/status` e recebe o diagnóstico da própria entrega.
- [x] Verificação não consome frase adicional além do necessário para o aceite, seguindo
      a mesma disciplina do aceite AWS já documentado (spec v1, seção 5).
- [x] Resultado documentado em `docs/27-aceite-real-do-irmao.md`, no mesmo padrão dos
      aceites anteriores.
