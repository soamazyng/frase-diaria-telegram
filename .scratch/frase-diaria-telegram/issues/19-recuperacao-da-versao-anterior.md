# 19 — Recuperação da versão anterior, caso a caso

**What to build:** quando uma publicação falha ou um PR é abandonado, o serviço volta sozinho para uma versão que funciona — sem reconstruir dependências, sem perder histórico e sem que um evento atrasado sobrescreva uma publicação mais recente.

**Blocked by:** 18 — Pipeline vinculado ao SHA e publicação serializada.

**Status:** ready-for-agent

- [ ] Artefatos imutáveis, configuração e manifesto suficientes para restaurar uma publicação sem reconstruir dependências ficam preservados.
- [ ] Dois marcos são mantidos e consultáveis: a publicação saudável anterior à tentativa e a versão estável aceita em `main`.
- [ ] Falha de deploy recupera a publicação saudável anterior à tentativa, considerando também o rollback nativo da infraestrutura (AC24).
- [ ] Falha do diagnóstico pós-publicação recupera a publicação saudável anterior à tentativa (AC24).
- [ ] Fechamento de PR sem merge, após várias candidatas, restaura a versão estável anterior ao PR — e não uma candidata do mesmo PR (AC25).
- [ ] Primeiro deploy sem versão anterior reverte os recursos de aplicação possíveis, deixa os envios desabilitados, preserva os dados já criados e documenta a ausência de versão recuperável (AC24).
- [ ] Antes de recuperar, confere-se se a publicação ativa ainda pertence à tentativa ou ao PR afetado; um evento antigo não sobrescreve uma publicação posterior (AC23).
- [ ] Repetir o evento de recuperação é idempotente.
- [ ] A recuperação usa o mesmo grupo de exclusão mútua da publicação, com verificação de atualidade **após** esperar — sem presumir ordem de chegada dos jobs.
- [ ] A versão restaurada é verificada e o resultado é guardado; falhando, o merge continua bloqueado, o diagnóstico é registrado no GitHub e um procedimento manual com o último artefato válido fica disponível.
- [ ] Novos envios são desabilitados quando não houver versão operacional verificável.
