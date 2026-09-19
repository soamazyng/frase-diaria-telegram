# Migração do OIDC e do arquivo de recuperação

Esta migração precisa ocorrer **antes** do primeiro push que use os workflows
novos. Ela troca a trust OIDC para o environment `producao`, cria o papel de
reconciliação e o bucket versionado de recuperação, e cadastra no GitHub apenas
referências operacionais. Nenhum token ou valor de SSM participa destes passos.

## Atualizar o bootstrap existente

Execute num terminal autenticado com o perfil de bootstrap. Em uma atualização,
o CloudFormation conserva os valores atuais dos parâmetros que não têm default.

```sh
aws cloudformation deploy \
  --template-file infra/bootstrap.yaml \
  --stack-name frase-diaria-bootstrap \
  --region us-east-1 \
  --profile perfil-padrao \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset
```

Para criar a stack do zero, informe também `--parameter-overrides` com o dono,
IDs imutáveis, repositório e bucket de staging do SAM obtidos na própria conta.
Não registre esses valores em arquivo, histórico de shell ou documentação.

## Configurar o GitHub sem imprimir os valores

O bloco abaixo cria o environment e faz *upsert* das três variáveis exigidas.
Os valores passam por memória e stdin; não são exibidos.

```sh
repositorio="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
politica_do_environment="$(jq -n \
  '{deployment_branch_policy:{protected_branches:false,custom_branch_policies:true}}')"
printf '%s' "$politica_do_environment" | gh api --method PUT \
  "repos/$repositorio/environments/producao" --input - >/dev/null

for branch in develop main; do
  if ! gh api "repos/$repositorio/environments/producao/deployment-branch-policies" \
    --jq '.branch_policies[].name' | grep -Fxq "$branch"; then
    gh api --method POST \
      "repos/$repositorio/environments/producao/deployment-branch-policies" \
      -f name="$branch" >/dev/null
  fi
done

valor_da_saida() {
  aws cloudformation describe-stacks \
    --stack-name frase-diaria-bootstrap \
    --region us-east-1 \
    --profile perfil-padrao \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" \
    --output text
}

definir_variavel() {
  nome="$1"
  valor="$2"
  corpo="$(jq -n --arg name "$nome" --arg value "$valor" '{name:$name,value:$value}')"
  if gh api "repos/$repositorio/actions/variables/$nome" >/dev/null 2>&1; then
    printf '%s' "$corpo" | gh api --method PATCH \
      "repos/$repositorio/actions/variables/$nome" --input - >/dev/null
  else
    printf '%s' "$corpo" | gh api --method POST \
      "repos/$repositorio/actions/variables" --input - >/dev/null
  fi
}

definir_variavel AWS_ROLE_PUBLICACAO_ARN "$(valor_da_saida PapelDePublicacaoArn)"
definir_variavel AWS_ROLE_RECONCILIACAO_ARN "$(valor_da_saida PapelDeReconciliacaoArn)"
definir_variavel AWS_BUCKET_ARTEFATOS "$(valor_da_saida BucketDeRecuperacaoNome)"
unset repositorio politica_do_environment branch corpo nome valor
```

Antes do push, confira somente os nomes, sem imprimir valores:

```sh
gh api "repos/{owner}/{repo}/actions/variables" --jq '.variables[].name'
```

O environment aceita somente `develop` e `main`, as duas branches usadas pelos
jobs privilegiados. O resultado das variáveis deve conter `AWS_ROLE_PUBLICACAO_ARN`,
`AWS_ROLE_RECONCILIACAO_ARN` e `AWS_BUCKET_ARTEFATOS`.

## Indexar o histórico de `/status`

Depois da publicação da aplicação, execute uma vez a migração aditiva abaixo.
Ela lê somente os campos mínimos das partes antigas e cria ponteiros por
destinatário e dia; não altera pedidos nem mensagens já enviadas.

```sh
TABELA_ESTADO="$(aws cloudformation describe-stacks \
  --stack-name frase-diaria-dados \
  --region us-east-1 \
  --profile perfil-padrao \
  --query "Stacks[0].Outputs[?OutputKey=='TabelaNome'].OutputValue | [0]" \
  --output text)" \
AWS_PROFILE=perfil-padrao \
AWS_REGION=us-east-1 \
uv run python -m frase_diaria.persistencia.migrar_status
```

A operação é idempotente: uma nova execução cria zero itens quando todos os
ponteiros já existem.
