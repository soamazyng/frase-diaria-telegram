# Pesquisa de segurança para o `AGENTS.md`

**Consulta:** 2026-09-07  
**Escopo:** Python/FastAPI em AWS Lambda, infraestrutura SAM e publicação por
GitHub Actions.  
**Método:** somente documentação oficial do GitHub, da AWS e repositórios das
actions mantidas pelos próprios fornecedores.

Este documento reúne regras que devem ser convertidas em instruções curtas e
imperativas no `AGENTS.md`. Ele não substitui `CLAUDE.md`, `rules.md` nem a spec;
serve para impedir que um agente transforme uma tarefa comum em vazamento de
credencial ou ampliação silenciosa de privilégio.

## Recomendações prioritárias

1. Proibir a impressão, cópia ou inclusão em commits de tokens, chaves, valores
   `SecureString`, conteúdo pessoal, cabeçalhos de autenticação, URLs assinadas e
   identificadores operacionais. Usar marcadores como `<ACCOUNT_ID>` e referências
   ao local seguro; não duplicar valores já presentes em documentação operacional.
2. Autenticar o GitHub na AWS exclusivamente com OIDC e credenciais temporárias;
   nunca criar `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` para o pipeline.
3. Negar permissões do `GITHUB_TOKEN` por padrão e liberar o mínimo por job;
   `id-token: write` somente no job que realmente assume o papel AWS.
4. Fixar toda action e workflow reutilizável externo por SHA completo e usar
   `persist-credentials: false` no checkout quando o job não precisa fazer push.
5. Não executar código, scripts, dependências ou artefatos de PR em workflows
   privilegiados (`pull_request_target`, `workflow_run`, `issue_comment`).
6. Manter papéis distintos para publicação da aplicação e alteração de
   infraestrutura; limitar ações e recursos AWS aos ARNs do projeto.
7. Manter os segredos do projeto em SSM Parameter Store como `SecureString`,
   concedendo só `ssm:GetParameter` sobre os parâmetros exatos à Lambda. Não
   colocar o valor do segredo em variável de ambiente da função.
8. Tratar logs como destino persistente: registrar por lista permitida de campos,
   nunca eventos HTTP completos, bodies, headers, exceções com credenciais ou
   respostas integrais de provedores.
9. Antes de publicar, executar testes, lint, `sam validate --lint`, validação das
   policies IAM e inspeção do change set. Publicar o artefato já avaliado e
   identificado por SHA/checksum, sem reconstruí-lo.

## GitHub Actions

### OIDC para AWS e credenciais temporárias

O GitHub recomenda OIDC para deixar de armazenar credenciais de nuvem de longa
duração, e a AWS recomenda que workloads usem papéis e credenciais temporárias.
O job precisa de `id-token: write` para solicitar o JWT; essa permissão apenas
habilita a obtenção do token e não concede escrita em outros recursos.
([GitHub — OIDC com AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws),
[AWS — IAM security best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html))

Padrão a registrar no `AGENTS.md`:

```yaml
permissions: {}

jobs:
  verificar:
    permissions:
      contents: read

  publicar:
    environment: producao
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@<SHA_COMPLETO> # versão humana
        with:
          persist-credentials: false
      - uses: aws-actions/configure-aws-credentials@<SHA_COMPLETO> # versão humana
        with:
          role-to-assume: <ARN_DO_PAPEL_DE_PUBLICACAO>
          aws-region: <REGIAO>
          role-session-name: github-${{ github.run_id }}
```

O repositório oficial `aws-actions/configure-aws-credentials` recomenda OIDC,
obtém credenciais de curta duração e sugere usar `github.run_id` no nome da
sessão para correlacionar ações nos logs de auditoria. A action remove as
credenciais do ambiente no pós-job por padrão; não definir
`AWS_SKIP_CLEANUP_STEP=true`, não exportar credenciais como outputs e não
gravá-las em perfil persistente.
([AWS action oficial — configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials))

### Trust policy do papel AWS

A trust policy deve validar `aud = sts.amazonaws.com` e restringir `sub` ao
repositório e à origem exata autorizada. A AWS alerta que omitir essa condição
permite que repositórios fora do controle do proprietário tentem assumir o papel;
wildcards amplos também devem ser evitados.
([AWS — role para GitHub OIDC](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html))

Há uma nuance atual importante: repositórios criados depois de 2026-07-15 usam,
por padrão, `sub` imutável com IDs do proprietário e do repositório; repositórios
anteriores conservam o formato antigo até optarem pela mudança. O agente deve
confirmar o formato real da claim e nunca inventá-lo. Sem environment, restringir
à branch autorizada; com `environment: producao`, o `sub` passa a identificar o
environment e deixa de conter a branch. Nesse caso, a própria AWS recomenda
adicionar a condição separada
`token.actions.githubusercontent.com:ref = refs/heads/develop`.
([GitHub — claims OIDC e formatos imutáveis](https://docs.github.com/en/actions/reference/security/oidc),
[AWS — Access Analyzer, condição de repositório e branch](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-reference-policy-checks.html))

OIDC precisa ser provisionado por bootstrap confiável antes do primeiro deploy.
O pipeline de aplicação não deve poder criar ou ampliar o próprio provedor OIDC,
a trust policy ou seu papel. Preservar a separação local já decidida entre papel
de publicação e papel de infraestrutura.

### Permissões mínimas do `GITHUB_TOKEN`

Declarar `permissions: {}` no topo e liberar por job somente o necessário. Ao
definir qualquer permissão explicitamente, as não listadas viram `none`; checkout
normal precisa apenas de `contents: read`. Evitar `write-all`, `read-all` e escrita
no nível do workflow quando apenas um job precisa dela.
([GitHub — sintaxe de `permissions`](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),
[GitHub — autenticação com `GITHUB_TOKEN`](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token))

Mesmo que o token não seja passado como input, uma action pode acessá-lo pelo
contexto `github.token`; por isso o controle efetivo é o escopo de `permissions`,
não a ausência de `${{ secrets.GITHUB_TOKEN }}` no YAML.
([GitHub — autenticação com `GITHUB_TOKEN`](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token))

### Segredos, mascaramento e logs do runner

O mascaramento automático não é garantia: transformações, Base64/URL encoding e
segredos estruturados podem impedir a correspondência exata. Valores sensíveis
gerados no job devem ser mascarados imediatamente com `::add-mask::`; não usar
`set -x`, `bash -x`, `--debug` nem comandos que despejem ambiente/configuração.
Se um segredo aparecer sem máscara, apagar o log da execução e rotacionar o
segredo — apenas ocultar a interface não o torna seguro.
([GitHub — uso seguro de Actions](https://docs.github.com/en/actions/reference/security/secure-use),
[GitHub — exclusão de logs de workflow](https://docs.github.com/en/rest/actions/workflow-runs#delete-workflow-run-logs))

Não escrever segredos em `$GITHUB_OUTPUT`, `$GITHUB_ENV`, artefatos ou caches; não
passá-los a actions de terceiros nem a passos que executem código não confiável.
Revisar logs de casos válidos e inválidos porque ferramentas podem enviar
argumentos e respostas para `stdout`/`stderr` inesperadamente. Se um valor
operacional não estiver cadastrado como GitHub Secret, aplicar `add-mask` antes
de qualquer comando que possa imprimi-lo.

### Inputs não confiáveis e triggers privilegiados

Não interpolar campos controláveis por autor de issue/PR diretamente em `run:`
ou `script:`. `${{ }}` é expandido antes de o shell executar; colocar o valor em
`env:` e usar a variável do shell entre aspas, ou passar como argumento a uma
action revisada.
([GitHub — mitigação de script injection](https://docs.github.com/en/actions/reference/security/secure-use#good-practices-for-mitigating-script-injection-attacks))

Evitar `pull_request_target`. Se for indispensável para rotular/comentar, não
fazer checkout, build, instalação, teste ou execução do código do PR.
`workflow_run` também é privilegiado: artefatos vindos de outro workflow são
dados não confiáveis e nunca devem ser executados; verificar explicitamente
`github.event.workflow_run.conclusion` antes de qualquer ação privilegiada. Em PR
de fork, preferir `pull_request`, que recebe token somente leitura e não recebe os
demais secrets. Mesmo que `actions/checkout` v7 bloqueie por padrão checkout
inseguro de fork nesses triggers, não ativar `allow-unsafe-pr-checkout` e não
contornar a proteção com `git fetch`, `gh pr checkout` ou download executável.
([GitHub — uso seguro de `pull_request_target`](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target))

### Supply chain, checkout e environments

SHA completo é a única referência de action que o GitHub considera imutável.
Tags e branches são móveis, inclusive para actions oficiais; guardar a versão
humana em comentário e usar Dependabot para propor atualizações revisáveis.
([GitHub — pinning por SHA](https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions))

`actions/checkout` mantém credencial Git utilizável por passos seguintes por
padrão. Definir `persist-credentials: false` sempre que não houver push explícito;
se houver push, isolá-lo em job próprio com permissão mínima e código confiável.
([actions/checkout — README oficial](https://github.com/actions/checkout/blob/main/README.md))

Usar environment `producao` e permitir deploy apenas da branch autorizada. No
plano GitHub Pro com repositório privado, environment secrets e restrições por
branch estão disponíveis, mas *required reviewers* e *wait timer* só estão
disponíveis em repositórios públicos nos planos Free/Pro/Team. Portanto, este
projeto não pode tratar aprovação obrigatória do environment como controle
existente; a aprovação manual deve continuar apoiada na proteção de branch e nos
checks obrigatórios.
([GitHub — deployments e environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments))

## AWS Lambda, IAM e segredos

### Menor privilégio e separação de papéis

Criar um papel de execução por função quando as permissões diferirem e limitar
ações aos recursos exatos. Evitar `Action: "*"`, `Resource: "*"`, policies
administrativas e AWS managed policies amplas no estado final. Usar IAM Access
Analyzer para validar a gramática e as práticas de segurança e para gerar/refinar
policies a partir da atividade observada no CloudTrail.
([AWS — IAM security best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html),
[AWS — validar policies com Access Analyzer](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html))

Para CI/CD, separar pelo menos:

- papel de validação/leitura, se a validação precisar consultar AWS;
- papel de publicação da aplicação, restrito às stacks e artefatos do projeto;
- papel de infraestrutura/bootstrap, sem uso no fluxo comum de deploy;
- papel de execução da Lambda, sem permissões de deploy ou administração IAM.

Restringir `iam:PassRole` ao papel de execução exato e, quando possível, à chamada
por CloudFormation/Lambda. Nenhum papel de runtime deve poder alterar o próprio
código, configuração, role ou parâmetros secretos.

### Variáveis de ambiente, Parameter Store e Secrets Manager

Variáveis de ambiente da Lambda são apropriadas para configuração operacional e
são criptografadas em repouso, mas a AWS recomenda não usá-las para API keys,
tokens ou outras informações sensíveis. O valor secreto deve ser obtido em tempo
de execução de um serviço de segredos.
([AWS Lambda — environment variables](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html),
[AWS Lambda — criptografia de environment variables](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars-encryption.html))

A recomendação geral da AWS para API keys e tokens é Secrets Manager, sobretudo
quando há rotação automática, acesso entre contas, replicação ou auditoria fina.
Este projeto, porém, já decidiu por SSM Parameter Store para manter custo
recorrente mínimo. O `AGENTS.md` deve preservar essa decisão e exigir controles
compensatórios: `SecureString`, nomes que não revelem o valor, acesso apenas aos
ARNs exatos e leitura com decriptação sem retorno/log do conteúdo.
([AWS — Parameter Store e `SecureString`](https://docs.aws.amazon.com/systems-manager/latest/userguide/what-is-a-parameter.html))

À função, conceder somente `ssm:GetParameter` para cada parâmetro necessário;
evitar `ssm:GetParametersByPath`, pois acesso a um caminho pode expor todos os
níveis abaixo dele. Não conceder `ssm:GetParameterHistory`, que também revela o
valor atual e versões anteriores. Com chave KMS gerenciada pelo cliente, limitar
`kms:Decrypt` à chave e ao encryption context dos parâmetros exatos.
([AWS — controle de acesso ao Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-setting-up.html),
[AWS — KMS para `SecureString`](https://docs.aws.amazon.com/systems-manager/latest/userguide/secure-string-parameter-kms-encryption.html))

O código pode manter cache em memória por ambiente de execução para reduzir
latência/chamadas, mas nunca deve persistir o segredo em `/tmp`, serializá-lo,
incluí-lo em exceptions ou devolvê-lo em resposta. A extensão oficial e o
Powertools oferecem cache local para Parameter Store e Secrets Manager.
([AWS Lambda — usar Parameter Store/Secrets Manager](https://docs.aws.amazon.com/lambda/latest/dg/with-secrets-manager.html))

### CloudWatch e política de logging

Lambda envia `stdout`/`stderr` ao CloudWatch Logs. Para este webhook FastAPI, a
regra deve ser por lista permitida: registrar IDs técnicos de correlação, estado,
latência e códigos de erro sanitizados; não registrar evento ASGI/APIGateway
completo, headers, body, query string, conteúdo da mensagem, resposta integral de
Telegram/Notion, valores SSM ou ambiente do processo. A AWS desaconselha
expressamente enviar dados sensíveis ao stdout de uma função.
([AWS — Serverless Applications Lens, proteção de dados](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/data-protection.html),
[AWS Lambda — logs](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-logs.html))

Preferir JSON estruturado com nomes de campo estáveis, sem anexar objetos brutos,
e manter a retenção finita já definida pelo projeto. CloudWatch Logs Data
Protection pode auditar e mascarar credenciais/PII e emitir
`LogEventsWithFindings`; é defesa em profundidade, não licença para logar dados.
A política só mascara eventos ingeridos depois de sua criação, e apenas usuários
sem `logs:Unmask` veem a versão mascarada.
([AWS — logging estruturado serverless](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/opex-logging.html),
[AWS — mascaramento no CloudWatch Logs](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/mask-sensitive-log-data.html))

## SAM, IaC e publicação segura

Executar `sam validate --lint` para validar YAML/JSON e as regras de recursos do
CloudFormation via `cfn-lint`. Como `sam validate` requer credenciais AWS, obtê-las
por OIDC com um papel mínimo; jamais introduzir access keys estáticas apenas para
essa etapa.
([AWS SAM — validação de templates](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-using-validate.html),
[AWS SAM — validação com `cfn-lint`](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/validate-cfn-lint.html))

Também validar documentos IAM com `aws accessanalyzer validate-policy`, tratando
`ERROR` e `SECURITY_WARNING` como bloqueantes e revisando warnings. A validação
oficial verifica gramática, práticas de segurança e recomendações acionáveis;
policies novas ou alteradas ainda precisam de teste antes de produção.
([AWS — policy validation](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html))

Gerar e inspecionar o change set antes de executá-lo. Change sets mostram quais
recursos serão criados/modificados e CloudFormation não aplica mudanças até a
execução; revisar especialmente alterações IAM, substituições/exclusões e os
recursos duráveis protegidos por `Retain`.
([AWS CloudFormation — `CreateChangeSet`](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_CreateChangeSet.html))

Nunca passar valor secreto como parâmetro de linha de comando, override SAM,
output, tag, nome de recurso ou texto livre: comandos e erros podem aparecer nos
logs, e metadados/nome de `SecureString` não são criptografados. O template deve
carregar somente nomes/ARNs de parâmetros; a Lambda busca o valor em runtime.

Preservar a ordem de publicação definida localmente: capturar SHA imutável,
verificar, construir uma vez, calcular checksum, revalidar atualidade após a fila
de exclusão mútua, publicar exatamente o artefato avaliado e executar smoke tests
sem enviar mensagem real. Credenciais temporárias não justificam ampliar a
sessão: usar a menor duração compatível e não reutilizá-las entre jobs.

## Checklist para o futuro `AGENTS.md`

- [ ] Manda ler `rules.md` antes de qualquer operação com segredos, AWS ou deploy.
- [ ] Proíbe revelar, repetir ou commitar valores/identificadores sensíveis.
- [ ] Define `permissions: {}` e permissões mínimas por job.
- [ ] Limita `id-token: write` ao job OIDC e proíbe access keys estáticas.
- [ ] Exige trust policy OIDC por repositório + branch/environment, sem wildcard.
- [ ] Registra a nuance do `sub` imutável introduzido em 2026-07-15.
- [ ] Proíbe execução de conteúdo não confiável em triggers privilegiados.
- [ ] Exige SHA completo para actions e `persist-credentials: false`.
- [ ] Explica a limitação de required reviewers no repo privado GitHub Pro.
- [ ] Mantém SSM `SecureString` e IAM por parâmetro exato, sem leitura por path.
- [ ] Proíbe logs de eventos/headers/bodies/respostas/segredos completos.
- [ ] Exige `sam validate --lint`, Access Analyzer e revisão de change set.
- [ ] Preserva build único, checksum, exclusão mútua e verificação de atualidade.
