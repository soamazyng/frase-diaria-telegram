# Bootstrap OIDC AWS e base do GitHub

> **Estado atual (auditoria de 2026-09-16):** os jobs privilegiados usam o
> environment `producao`; as trusts exigem ao mesmo tempo esse environment e o
> `ref` exato (`develop` para publicação, `main` para reconciliação). O segundo
> papel chama-se `frase-diaria-reconciliacao`. ARNs e o bucket de artefatos são
> configurados em variáveis do repositório e não ficam versionados. Os relatos
> abaixo preservam o contexto histórico do ticket 16.

## Comportamento

O GitHub Actions já pode assumir papel na AWS com credenciais temporárias,
sem nenhuma chave de longo prazo guardada no repositório. Três recursos
existem agora na conta `<AWS_ACCOUNT_ID>` (`us-east-1`), publicados uma única
vez, pela identidade já autorizada `user/aws-developer-group`:

- **Provedor OIDC** — `token.actions.githubusercontent.com`, com
  `ClientIdList: [sts.amazonaws.com]`.
- **`frase-diaria-publicacao`** — assumido pelo workflow de push em
  `develop` (tickets 17/18, ainda não construídos); publica a stack
  `frase-diaria-app`.
- **`frase-diaria-reconciliacao`** — assumido pelo workflow periódico de
  reconciliação de publicações (ticket 20, ainda não construído); por
  enquanto só lê o estado da stack, porque a lógica de recuperação em si
  ainda não existe.

Os dois papéis confiam exclusivamente em `<GITHUB_OWNER>/frase-diaria-telegram`,
validam `aud=sts.amazonaws.com`, restringem `sub` ao environment de produção e
validam a branch exata numa condição separada (`develop` para publicação,
`main` para reconciliação) — nunca
`StringLike` com curinga, porque os dois valores são conhecidos e exatos
(AC28). `id-token: write` não foi concedido a workflow nenhum ainda, porque
nenhum workflow existe: fica registrado aqui como responsabilidade de quem
escrever os workflows dos tickets 17/18/20 — só o job que assume papel AWS
pode ter essa permissão.

O repositório já era privado, com `main` como branch padrão; `develop`
existia localmente (com o histórico completo dos tickets 01–15) mas nunca
tinha sido enviada ao GitHub — foi enviada agora, pela primeira vez, com a
mesma raiz histórica de `main` (confirmado antes do push: `git merge-base
develop origin/main` aponta para o commit inicial). `main` não foi alterada:
inicializá-la com o necessário para os workflows é literalmente o que os
tickets 17/18/20 fazem ao adicionar os arquivos de workflow, e nenhuma
publicação do bot é necessária antes disso.

## Decisão técnica

**Template CloudFormation separado (`infra/bootstrap.yaml`), não SAM.** Este
bootstrap não declara função Lambda nenhuma — é só o provedor OIDC e dois
papéis IAM — então não precisa do `Transform: AWS::Serverless-2016-10-31`
nem do empacotamento do SAM. Fica fora do ciclo de vida das stacks de dados e
aplicação: não referencia nem é referenciado por nenhuma delas.

**Duas trust policies, uma por branch, não uma só com `sub` em lista.** A
spec pede papéis separados para publicação e infraestrutura (4.10); mantê-los
como recursos IAM distintos, cada um confiando só na branch que efetivamente
o assume, é o que torna a restrição de `sub` precisa em vez de uma lista que
autorizaria qualquer um dos dois workflows a assumir qualquer um dos dois
papéis.

**Permissões do papel de publicação levantadas do template real
(`infra/aplicacao.yaml`), não de suposição.** Antes de escrever a policy,
consultei a stack `frase-diaria-app` já publicada (`aws cloudformation
list-stack-resources`) para conferir os tipos de recurso reais: funções
Lambda, API HTTP v2, grupos de log, e os papéis de execução que o SAM
gerencia. A policy cobre exatamente esses tipos, com recurso escopado por
prefixo (`frase-diaria-*`) em vez de `Resource: "*"`. Duas exceções
justificadas, revisadas neste diff:

- `apigateway:POST` sobre `arn:.../apis*` — a criação de sub-recursos (rota,
  integração, estágio) não tem ARN previsível antes de existir, e o suporte
  de `aws:ResourceTag` do API Gateway a essa operação específica não foi
  verificado ao vivo (ver achado do `security-review` abaixo). Residual
  aceito deliberadamente, documentado no próprio template para o ticket 18
  revisitar contra o pipeline real.
- `iam:PassRole` e gestão dos papéis de execução, escopados a
  `frase-diaria-app-*` — inevitável para o SAM gerenciar os papéis de
  execução das próprias funções que ele declara; sem isso nenhum deploy
  funcionaria. Restrito ao prefixo da stack de aplicação para que um
  `PassRole` combinado com `UpdateFunctionConfiguration` não alcance nenhum
  papel fora dele — inclusive nunca os dois papéis deste próprio bootstrap
  (achado de escalonamento de privilégio verificado via skill `aws-iam`).

**Papel de infraestrutura deliberadamente mínimo.** Só leitura
(`DescribeStacks`, `GetTemplate`, `GetFunction`). O ticket 20, que ainda não
foi implementado, vai decidir exatamente que ação de recuperação esse papel
precisa executar; conceder isso agora seria antecipar um desenho que ainda
não existe.

## Verificação

- `aws cloudformation validate-template` no `infra/bootstrap.yaml`: OK.
- Publicação real: `aws cloudformation deploy --stack-name
  frase-diaria-bootstrap` — `CREATE_COMPLETE` nos três recursos
  (`ProvedorOIDCDoGitHub`, `PapelDePublicacao`, `PapelDeReconciliacao`).
  Executado por `user/aws-developer-group`, a identidade já verificada no
  ticket 01.
- Nenhum segredo foi tocado: o bootstrap não usa SSM nem gera chave alguma.
  Identificadores operacionais, inclusive ARNs, ficam fora dos arquivos
  versionados conforme a política atual do repositório.
- Políticas efetivas do GitHub verificadas via `gh api`:
  `actions/permissions` → Actions habilitado, `allowed_actions: all`;
  `actions/permissions/workflow` → `default_workflow_permissions: read`,
  `can_approve_pull_request_reviews: false`. `allowed_actions: all` e a
  ausência de exigência de SHA-pin (`sha_pinning_required: false`) são
  candidatos a endurecimento quando os workflows reais existirem (tickets
  17/18), não bloqueiam este ticket. A permissão específica de "Actions
  criarem PR" não apareceu como campo separado nesta consulta — pode ser uma
  particularidade de conta pessoal (não organização); fica para validação
  prática quando o ticket 17 tentar criar o primeiro PR de verdade, que é o
  teste que realmente prova essa permissão (AC19).
- `develop` enviada ao GitHub pela primeira vez (`git push -u origin
  develop`), confirmando antes que compartilha a raiz histórica de `main`
  (`git merge-base develop origin/main` = commit inicial). `main` não foi
  tocada.

## Review

Não se aplica o `/code-review` de Standards/Spec em dois eixos (não há código
Python). Em vez disso, rodei a skill `security-review` focada só em
`infra/bootstrap.yaml`, dado que este ticket cria confiança IAM real — a
superfície mais sensível que um único arquivo pode ter neste projeto.

Achados: confiança OIDC (`aud`/`sub` via `StringEquals`, sem curinga) e o
escopo de `iam:PassRole`/gestão de papéis de execução (restrito ao prefixo
`frase-diaria-app-*`, não alcança nenhum papel fora dele, inclusive os dois
deste próprio bootstrap) — confirmados corretos. Um achado de severidade
média, real e corrigido: `apigateway:*` sobre `arn:.../apis*` não distinguia
a API HTTP deste projeto de qualquer outra API HTTP que existisse na mesma
conta/região — a conta é de projeto único hoje, então o risco concreto atual
era zero, mas a policy em si não impunha esse limite, o que contraria a
exigência do `AGENTS.md` de toda ação-curinga ter uma condição que reduza o
alcance. Corrigido: as ações que operam sobre a API já existente
(`GET`/`PUT`/`PATCH`/`DELETE`) ganharam a condição
`aws:ResourceTag/aws:cloudformation:stack-name = frase-diaria-app` — tag que
o próprio CloudFormation já aplica automaticamente, sem exigir nenhuma
mudança em `infra/aplicacao.yaml`. `apigateway:POST` (criação de
sub-recursos) ficou sem essa condição, documentado como residual aceito: não
verifiquei ao vivo se o API Gateway aplica `aws:ResourceTag` a essa operação
específica, e testar às cegas contra o papel já publicado era mais arriscado
que registrar a lacuna para o ticket 18 confirmar contra o pipeline real.
Stack republicada (`UPDATE_COMPLETE`) com a correção antes do commit.

## Próximo passo

O próximo ticket elegível por dependência é o **17 — PR automático develop →
main**, que finalmente usa a confiança OIDC criada aqui. A recomendação de
endurecimento do GitHub Actions (`allowed_actions`, SHA-pin) fica registrada
para quando os primeiros workflows reais forem escritos.
