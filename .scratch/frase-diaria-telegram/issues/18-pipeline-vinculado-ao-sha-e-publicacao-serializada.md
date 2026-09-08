# 18 — Pipeline vinculado ao SHA e publicação serializada

**What to build:** o que foi testado é exatamente o que vai para produção. Cada push em `develop` avalia um SHA imutável, constrói o artefato uma única vez, entra numa exclusão mútua de produção, publica aquele artefato e verifica a saúde do resultado — tudo antes do merge, porque só existe um ambiente de produção.

**Blocked by:** 03 — Publicação manual em SAM: /health vivo na AWS; 17 — PR automático develop → main.

**Status:** implementado em 2026-09-08, verificação local completa — ver
`docs/18-pipeline-vinculado-ao-sha-e-publicacao-serializada.md`. Falta a
publicação real (primeiro push autorizado para `develop` executando o job
`publicar` contra GitHub/AWS de verdade); só fecha como concluído depois
disso.

- [ ] O SHA imutável do push é capturado e o PR correspondente é localizado.
- [ ] Testes, análise estática e validação SAM rodam contra esse SHA; qualquer falha impede a publicação e deixa o merge bloqueado (AC20).
- [ ] O artefato é construído uma única vez e identificado por SHA e checksum.
- [ ] A publicação entra numa exclusão mútua de produção e, após esperar, reconsulta o PR aberto e o SHA atual em vez de presumir ordem de chegada dos jobs.
- [ ] Publicação em andamento é registrada e a elegibilidade de merge da candidata anterior é invalidada.
- [ ] Exatamente o artefato avaliado é publicado.
- [ ] A verificação pós-publicação confere saúde, versão ativa, acesso às dependências e configuração de webhook e agendamento, sem consumir frase nem enviar mensagem de teste.
- [ ] Sucesso é registrado somente no SHA efetivamente publicado e ainda atual no PR (AC21).
- [ ] Um push durante a publicação não permite que o resultado antigo aprove o novo commit (AC22).
- [ ] Antes de publicar, exige-se que o conteúdo de `develop` inclua a base relevante de `main`.
- [ ] Apenas trabalhos sem mutação podem ser cancelados livremente.
- [ ] Indisponibilidade detectada no diagnóstico reprova a publicação.
