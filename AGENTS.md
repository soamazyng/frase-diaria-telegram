# AGENTS.md

Instruções para agentes que trabalham neste repositório. Mantenha este arquivo curto e
operacional; detalhes de produto, incidentes e justificativas permanecem nas fontes indicadas.

## Contexto obrigatório

- Antes de alterar código ou testes, leia `contextIA/Spec-Frase-Diaria-Telegram.md` e as seções
  relevantes de `CLAUDE.md`. Toda mudança de produto deve mapear para um critério de aceite (AC);
  o que não mapeia é escopo novo e exige decisão da usuária.
- Segurança AWS/GitHub Actions: antes de alterar `infra/`, `.github/workflows/`, autenticação,
  logs, publicação, integrações com credencial ou segredos, leia `rules.md` e
  `docs/pesquisa-agents-seguranca.md` por inteiro.
- `rules.md` é a fonte de verdade das armadilhas operacionais já ocorridas. Não duplique suas
  receitas aqui nem substitua um teste real por uma suposição sobre YAML ou permissões.
- Preserve alterações existentes no diretório de trabalho. Inspecione `git status` e os diffs
  relevantes antes de editar; não descarte trabalho que não foi criado na tarefa atual.

## Projeto e limites arquiteturais

- Serviço Python 3.13 com FastAPI e Mangum, executado em AWS Lambda e declarado com AWS SAM.
  Entradas HTTP e agendadas convergem em casos de uso; estado durável vive no DynamoDB.
- `dominio/` contém regras puras. `aplicacao/` coordena casos de uso e define portas.
  Frameworks, SDKs e formatos de evento pertencem aos adaptadores de `infraestrutura/`.
- `dominio/` e `aplicacao/` não importam FastAPI, Mangum, Starlette, boto3 ou botocore. Crie uma
  porta em `aplicacao/portas.py` e implemente o adaptador na infraestrutura.
- Relógio, aleatoriedade, persistência e integrações externas devem ser substituíveis nos testes.
  Não use tarefas em background depois que a resposta HTTP foi devolvida.
- Preserve idempotência e concorrência com escritas condicionais, transações e identidades
  persistentes. Uma retentativa reutiliza a reserva; resultado externo ambíguo nunca autoriza
  reenvio automático cego.
- Recursos duráveis e recursos de aplicação permanecem em stacks separadas. Mudanças de dados
  são aditivas e compatíveis; retenção, proteção contra exclusão e recuperação pontual não podem
  ser enfraquecidas sem uma decisão explícita.
- Este projeto tem um único ambiente de produção. Não publique, registre webhook, altere segredos
  nem crie/remova recursos AWS sem autorização explícita na tarefa atual.

## Desenvolvimento e verificação

- **Implementação, correção ou refatoração:** antes de editar, leia e siga a seção
  “Implementação: Clean Code e skills obrigatórias” de `rules.md`, inclusive ao continuar uma
  task/ticket/spec. Ela exige `/implement` + `/python-clean-code`, testes e `/code-review` final.
- **Padrão obrigatório de issue:** ao concluir uma task/ticket, atualize o arquivo da issue em
  `.scratch/frase-diaria-telegram/issues/<numero>-<nome>.md` para o padrão abaixo:
  - `Status: concluído em YYYY-MM-DD — ver `docs/<numero>-<nome>.md``
  - marcar todos os itens de checklist como `[x]`
  - usar o mesmo padrão da issue 06/07, sem “ready-for-agent” nem “implemented” em arquivo finalizado
- **Commit por ticket:** cada task/ticket concluída deve ter um commit separado, com mensagem
  clara e escopo do ticket. O commit inclui apenas os arquivos pertencentes à task atual; nunca
  misture mudanças de outra issue, trabalho em andamento ou limpeza do diretório.
- O commit final exigido por `/implement` inclui somente arquivos pertencentes à task atual. Nunca
  misture mudanças preexistentes ou de outra pessoa e nunca descarte alterações para limpar o
  diretório de trabalho.
- Use `uv` e o `uv.lock`; não use `pip` diretamente nem crie outro ambiente virtual.
- Instalação: `make instalar`.
- Testes: `make teste`; teste focal:
  `uv run pytest caminho/do/teste.py::nome_do_teste`.
- Estática e formatação: `make lint`; correção automática: `make formatar`.
- Gate local completo: `make verificar`.
- Implemente em fatias pequenas e testáveis. Para correção de bug, primeiro obtenha um teste que
  reproduza o defeito; para uma nova invariante, quebre-a deliberadamente, confirme que o teste
  fica vermelho e restaure a implementação.
- Teste comportamento observável e contratos públicos, não métodos privados. Cubra fronteiras
  HTTP, persistência, idempotência, concorrência e sanitização quando a mudança as tocar.
- Ao alterar templates SAM, valide os dois templates com a versão atual do SAM CLI usada pelo
  projeto e revise qualquer mudança de IAM, retenção, criptografia ou política de exclusão.
- Conclusão: os testes focais passam, `make verificar` passa e todo gate adicional da área alterada
  foi executado. Se algo não puder ser executado, informe exatamente o que faltou e por quê.

## Proteção de segredos e dados sensíveis

- Considere sensíveis: credenciais e tokens; IDs de conta, conversa, bot e recursos; ARNs e URLs
  operacionais; conteúdo pessoal; payloads de webhook; URLs assinadas; valores de parâmetros;
  saídas derivadas ou codificadas desses dados. Use marcadores fictícios em código, testes, docs,
  commits, issues, PRs e respostas.
- O fato de um identificador já aparecer em `CLAUDE.md`, no histórico Git ou numa saída de CLI não
  autoriza reproduzi-lo. O `AGENTS.md` nunca deve conter valores reais.
- Leia apenas nomes e metadados quando bastarem. Nunca imprima arquivos de credenciais, `.env`,
  payloads completos, contextos do GitHub, todas as variáveis de ambiente ou respostas brutas de
  serviços. Faça consultas mínimas e aplique projeção ou redação antes da saída.
- A usuária cadastra valores secretos em um terminal separado. Não solicite que sejam colados na
  conversa, em argumentos visíveis, no workflow ou em arquivos versionados.
- Em runtime, busque segredos do SSM Parameter Store como `SecureString` com IAM mínimo. Variáveis
  de ambiente carregam configuração não secreta ou referências, não tokens em texto puro.
- Mantenha segredos apenas pelo tempo necessário, não use `set -x`/`bash -x`, não faça `echo` e não
  os grave em artefatos, caches, outputs, traces ou mensagens de erro. Sanitização e mascaramento
  são defesa adicional, não permissão para produzir o valor.
- Exceções de integrações devem omitir URLs, cabeçalhos, corpos e encadeamentos que possam conter
  credenciais. Logs e endpoints de saúde/status expõem apenas códigos, estados e correlações
  sanitizados — nunca conteúdo pessoal ou configuração interna.
- Se houver suspeita de exposição, interrompa a propagação: não repita o valor, identifique apenas
  o local e o tipo, remova o log/artefato quando autorizado e recomende revogação ou rotação
  imediata. Registre o incidente sem registrar o segredo.

## GitHub Actions seguro

- Todo workflow começa com `permissions: {}` ou `contents: read`; conceda permissões adicionais no
  menor job possível. `id-token: write` existe somente no job que assume o papel AWS.
- Autentique na AWS por OIDC e credenciais temporárias. A trust policy restringe `aud` e `sub` ao
  repositório, branch/tag ou environment esperado; não armazene access keys AWS no GitHub.
- Separe jobs sem privilégio (checkout, instalação, lint, testes e build) do job de produção. O job
  privilegiado consome somente artefato verificado, exige dependências concluídas e usa o
  environment protegido de produção.
- Não execute código, scripts, ações ou artefatos não confiáveis em jobs com segredos, OIDC ou
  token de escrita. Evite `pull_request_target`; em `workflow_run`, valide origem e SHA e trate
  artefatos recebidos como entrada não confiável.
- Dados controláveis por PR, issue, comentário, branch ou commit não entram diretamente em
  `run:`/`script:`. Passe-os por variável de ambiente, trate-os como dados e sempre cite expansões
  de shell. Não escreva entrada não confiável sem delimitação segura em `GITHUB_ENV` ou
  `GITHUB_OUTPUT`.
- Fixe cada `uses:` em SHA completo e mantenha a versão legível em comentário. Revise a origem da
  ação e habilite atualização automatizada específica para GitHub Actions.
- Use `actions/checkout` com `persist-credentials: false` quando as credenciais Git não forem
  indispensáveis, especialmente antes de executar código não confiável.
- Não despeje contexts, eventos, ambientes ou respostas de API nos logs. Registre valores
  derivados sensíveis com `::add-mask::` antes de qualquer uso e revise logs de caminhos de
  sucesso e erro; a redação automática do GitHub não é garantia.
- Faça build uma vez. Identifique o artefato pelo SHA imutável e checksum e publique exatamente o
  que passou pelos gates. Jobs que mutam produção não usam cancelamento livre.
- Publicação e recuperação compartilham exclusão mútua. Depois de esperar pela trava, reconfirme
  PR aberto, SHA atual e versão ativa antes de qualquer mutação; merge permanece manual.

## AWS Lambda e infraestrutura

- Aplique menor privilégio por função, ação e ARN. Um curinga exige justificativa, condição que
  reduza o alcance e revisão explícita no diff; papel de infraestrutura não é papel de publicação.
- Configuração operacional pode usar variáveis de ambiente; segredos e dados sensíveis ficam no
  SSM e são buscados em runtime. Considere o cache do ambiente Lambda ao planejar rotação e
  republicação.
- Trate o ambiente de execução como reutilizável, porém efêmero: cacheie apenas clientes e dados
  não sensíveis apropriados; grave estado permanente antes de encerrar e não deixe dados da
  usuária em globais ou `/tmp` além da invocação necessária.
- Logs do CloudWatch têm retenção explícita e conteúdo estruturado mínimo. Não registre eventos
  completos, headers, payloads do Telegram/Notion, conteúdo de frases, parâmetros ou respostas que
  possam carregar tokens.
- Antes de sondar permissões ou criar recursos, liste o estado atual e use uma operação realmente
  não mutante ou uma entrada inválida comprovadamente segura. As exceções e incidentes conhecidos
  estão em `rules.md`.
- Preserve a arquitetura sem VPC/NAT enquanto não houver requisito aprovado. Qualquer novo serviço
  exige estimativa de custo e atualização da documentação de custo.

## Entrega da tarefa

Relate, nesta ordem: comportamento implementado; decisão técnica; o que os testes demonstram;
próximo passo. Inclua riscos, verificações não executadas e qualquer efeito inesperado. Não inclua
valores sensíveis nem copie saídas brutas para provar a execução.
