# 27 — Aceite real com o irmão como destinatário

**What to build:** o irmão da usuária é cadastrado como destinatário de verdade, recebe
a diária real e usa `/frase` e `/status` na própria conta do Telegram — validação fora
de fixtures, no ambiente de produção único do projeto.

**Blocked by:** 24 — Autorização e comandos reconhecem múltiplos destinatários;
25 — Diária com múltiplos destinatários: entrega compartilhada e falhas independentes;
26 — `/status` reporta a entrega do próprio destinatário.

**Status:** ready-for-agent — indicação documental, sem label aplicada a um rastreador.

- [ ] Chat_id do irmão cadastrado no SSM pela usuária, fora da conversa com o agente
      (rules.md).
- [ ] Irmão recebe a diária real, com o mesmo conteúdo entregue à usuária no mesmo dia.
- [ ] Irmão usa `/frase` e recebe uma frase extra própria.
- [ ] Irmão usa `/status` e recebe o diagnóstico da própria entrega.
- [ ] Verificação não consome frase adicional além do necessário para o aceite, seguindo
      a mesma disciplina do aceite AWS já documentado (spec v1, seção 5).
- [ ] Resultado documentado em `docs/27-aceite-real-do-irmao.md`, no mesmo padrão dos
      aceites anteriores.