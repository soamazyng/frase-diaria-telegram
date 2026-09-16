# Publicação manual na AWS

**Ticket:** 03 — Publicação manual em SAM: `/health` vivo na AWS
**Primeira publicação:** 2026-09-07

Este documento descreve a publicação **manual**, feita da máquina da
desenvolvedora. A automação vem no ticket 18; até lá, é assim que se publica.

## Duas stacks, de propósito

| Stack | Arquivo | Contém | Muda quando |
|---|---|---|---|
| `frase-diaria-dados` | `infra/dados.yaml` | tabela DynamoDB | quase nunca |
| `frase-diaria-app` | `infra/aplicacao.yaml` | Lambda, HTTP API, log group, role | a cada publicação |

A separação é a razão de o histórico sobreviver: a tabela tem `DeletionPolicy:
Retain` e `UpdateReplacePolicy: Retain`, e a stack de aplicação apenas **importa**
o nome e o ARN dela via `Fn::ImportValue`. Republicar, atualizar ou até excluir a
aplicação não alcança os dados.

O acoplamento por *export/import* também protege na direção contrária: enquanto a
stack de aplicação existir, o CloudFormation recusa excluir a tabela exportada.

## Pré-requisitos

- Perfil AWS configurado (`perfil-padrao`, conta <AWS_ACCOUNT_ID>, região `us-east-1`).
- `uv` instalado. O SAM CLI roda via `uvx`, sempre em versão atual — o SAM
  instalado na máquina pode ser antigo demais para o runtime escolhido.

## Publicar

```sh
make publicar-dados                      # uma vez, na primeira instalação
make publicar-app                        # a cada versão
VERSAO=$(git rev-parse HEAD) make publicar-app   # identificando o commit
```

O parâmetro `Versao` é o que `GET /health` devolve. O pipeline do ticket 18 passa
aqui o SHA avaliado, e é assim que o AC21 confere se o que está no ar é o que foi
testado. Sem o parâmetro, a versão publicada fica `desenvolvimento`.

## Verificar

```sh
curl https://<API_ID>.execute-api.us-east-1.amazonaws.com/health
```

Resposta esperada:

```json
{"situacao":"ok","versao":"<sha>","instante":"2026-09-07T16:15:06.692181+00:00"}
```

## Como o empacotamento funciona

O `Metadata: BuildMethod: makefile` faz o SAM chamar o alvo `build-Funcao` do
Makefile, que:

1. exporta as dependências de produção do `uv.lock` (sem as de desenvolvimento);
2. instala **para `aarch64-manylinux2014` e Python 3.13**, não para a máquina local;
3. copia `src/frase_diaria` para dentro do artefato;
4. remove `__pycache__`.

O passo 2 é o que não pode ser esquecido: instalar as dependências no macOS
produziria um `_pydantic_core` de macOS, e a função quebraria **em execução**, não
no build. Para conferir um artefato:

```sh
file .aws-sam/build/Funcao/pydantic_core/_pydantic_core*.so
# esperado: ELF 64-bit LSB shared object, ARM aarch64
```

## Estado verificado em 2026-09-07

| Item | Verificação |
|---|---|
| `GET /health` público | HTTP 200; 2,7 s a frio, 0,65 s morno |
| Versão publicada | reflete o parâmetro `Versao` |
| Criptografia da tabela | `SSEDescription.Status = ENABLED` |
| Point-in-time recovery | `ENABLED` |
| Cobrança da tabela | `PAY_PER_REQUEST` (sem capacidade provisionada) |
| Runtime / arquitetura | `python3.13` / `arm64` / 128 MB |
| VPC | nenhuma — `VpcConfig.VpcId` vazio, sem NAT |
| Retenção de logs | 14 dias |
| Permissões da função | policy inline restrita à tabela do projeto, mais `AWSLambdaBasicExecutionRole` |

**Independência entre as stacks — exercitada, não presumida.** Foi gravado um item
na tabela, a aplicação foi republicada com outra versão, e o item foi lido de
volta intacto depois. A versão em `/health` mudou de `ticket03-manual` para
`ticket03-republicado`, provando que o deploy de fato ocorreu. O item de teste foi
removido em seguida.

## Nota sobre custo

A tabela é on-demand e o volume é irrisório, mas o **Point-in-Time Recovery cobra
por GB-mês armazenado**. Com poucos megabytes, é fração de centavo; ainda assim é
o único item desta stack que não é estritamente gratuito. A alternativa seria
desligá-lo e confiar apenas no `Retain`, ao custo de não poder restaurar a tabela
a um instante anterior. Mantido ligado por causa da exigência da spec de não
perder histórico.

## Desfazer

```sh
uvx --from aws-sam-cli sam delete --stack-name frase-diaria-app --region us-east-1
```

Excluir a stack de aplicação **não** remove a tabela. Para remover os dados é
preciso excluir a stack de dados e, como a tabela é `Retain`, apagá-la
explicitamente depois — dois passos deliberados, nunca um acidente.
