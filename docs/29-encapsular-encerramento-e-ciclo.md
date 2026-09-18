# Ticket 29 — Encapsular encerramento do pedido e avanço do ciclo

## Comportamento implementado

O encerramento posterior à tentativa de entrega passou a ser executado por
`EncerrarPedido`. O módulo recebe o contexto do ciclo e o resultado tipado da entrega,
persiste o estado correspondente do pedido e então consome ou libera a frase. Conclusão
consome uma vez; entrega parcial ou incerta consome com ressalva; falha comprovada sem
envio e expiração sem confirmação liberam a reserva.

Conflitos ao salvar o ciclo releem o estado vigente e reaplicam apenas a mutação local.
Essa retentativa não chama o canal externo. `ProcessarPedido` ficou responsável pelo
lease, escolha e reserva da frase, preparação do pedido e coordenação dos módulos de
entrega e encerramento.

Não houve mudança no contrato HTTP, nos eventos Lambda ou no formato persistido.

## Decisão técnica

O seam foi colocado depois de `EntregadorDePedido`, aproveitando `ResultadoDaEntrega` como
fonte única do pedido e do desfecho. `ContextoDoEncerramento` reúne somente ciclo, versão e
sequencial; assim não é possível combinar silenciosamente o pedido de uma entrega com
outro pedido duplicado no contexto. Operações anteriores à entrega recebem o pedido de
forma explícita.

A política de contenção recebe espera e dispersão por injeção. O despacho por
`DesfechoDaEntrega` é exaustivo para que um novo valor do enum gere erro de análise
estática até ser tratado. A ordem pedido antes de ciclo preserva uma referência durável à
reserva caso a execução seja interrompida.

Foram aplicadas as skills `implement`, `python-clean-code`, `codebase-design`, `tdd` e
`code-review`. A mudança reduz as responsabilidades e os níveis de abstração de
`ProcessarPedido` (G6, G30 e G34), evita argumentos de flag (F3), mantém dependências
substituíveis e torna combinações inválidas menos representáveis (G26).

## Testes e verificações

O primeiro teste do seam falhou antes da implementação porque o módulo ainda não existia.
Depois da extração, ele demonstrou a conclusão e o consumo do ciclo. O review mostrou que
uma única chamada não provava idempotência; o teste foi reforçado para repetir o
encerramento com a versão original, provocar a releitura do ciclo já consumido e confirmar
que o contador e a versão permanecem em uma única entrega.

A suíte focal de `ProcessarPedido` passou com 71 testes. O gate `make verificar` passou
com Ruff, verificação de formato, mypy e 492 testes. Permaneceram apenas avisos de
depreciação de dependências já existentes.

## Code-review

O primeiro review encontrou três pontos no eixo Standards: estado duplicado entre contexto
e resultado, prova insuficiente de idempotência e despacho não exaustivo do enum. Todos
foram corrigidos. O eixo Spec não encontrou desvio comportamental.

O re-review do código corrigido concluiu **Standards: OK** e **Spec: OK**, sem achados
pendentes sobre os AC03, AC04, AC13, AC14 e AC32–AC35.

## Próximo passo

O próximo ticket do plano pode continuar a redução de `ProcessarPedido` usando os módulos
de entrega e encerramento como contratos estáveis.
