# 18 — Pipeline vinculado ao SHA e publicação serializada

**What to build:** o que foi testado é exatamente o que vai para produção. Cada push em `develop` avalia um SHA imutável, constrói o artefato uma única vez, entra numa exclusão mútua de produção, publica aquele artefato e verifica a saúde do resultado — tudo antes do merge, porque só existe um ambiente de produção.

**Blocked by:** 03 — Publicação manual em SAM: /health vivo na AWS; 17 — PR automático develop → main.

**Status:** concluído em 2026-09-08 — ver
`docs/18-pipeline-vinculado-ao-sha-e-publicacao-serializada.md`.

- [x] O SHA imutável do push é capturado e o PR correspondente é localizado.
- [x] Testes, análise estática e validação SAM rodam contra esse SHA; qualquer falha impede a publicação e deixa o merge bloqueado (AC20).
- [x] O artefato é construído uma única vez e identificado por SHA e checksum.
- [x] A publicação entra numa exclusão mútua de produção e, após esperar, reconsulta o PR aberto e o SHA atual em vez de presumir ordem de chegada dos jobs.
- [x] Publicação em andamento é registrada e a elegibilidade de merge da candidata anterior é invalidada.
- [x] Exatamente o artefato avaliado é publicado.
- [x] A verificação pós-publicação confere saúde, versão ativa, acesso às dependências e configuração de webhook e agendamento, sem consumir frase nem enviar mensagem de teste.
- [x] Sucesso é registrado somente no SHA efetivamente publicado e ainda atual no PR (AC21).
- [x] Um push durante a publicação não permite que o resultado antigo aprove o novo commit (AC22).
- [x] Antes de publicar, exige-se que o conteúdo de `develop` inclua a base relevante de `main`.
- [x] Apenas trabalhos sem mutação podem ser cancelados livremente.
- [x] Indisponibilidade detectada no diagnóstico reprova a publicação.
