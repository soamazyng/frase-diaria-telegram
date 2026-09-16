# Ticket 28 — Extrair a entrega por destinatário

## Comportamento implementado

A entrega de uma frase passou a ser executada por `EntregadorDePedido`. O módulo tenta
cada parte de cada destinatário, persiste intenção antes da chamada externa, registra
confirmação ou incerteza e devolve um resultado agregado ao coordenador. Falhas de um
destinatário continuam sem impedir a tentativa aos demais, e ambiguidades continuam
suspendendo reenvio automático.

`ProcessarPedido` recebe o entregador pronto na composição. Ele não conhece mais o canal
externo, o cálculo de backoff nem as operações que registram intenção, confirmação ou
incerteza; permanece responsável pela reserva, pelo lease, pelas consultas necessárias à
seleção, pelo estado final do pedido e pelo ciclo.

Não houve mudança no contrato HTTP, nos eventos Lambda ou no formato persistido.

## Decisão técnica

O seam foi colocado entre a tentativa de entrega e o encerramento do pedido. A interface
do entregador recebe pedido, frase e sequencial e devolve `ResultadoDaEntrega`, que reúne
o pedido atualizado, o desfecho agregado, o motivo, eventual próxima tentativa e a
existência de confirmação.

As dependências de persistência, canal, relógio e dispersão são injetadas. A composição de
produção fornece a dispersão aleatória; os testes fornecem uma implementação determinística.
O resultado valida que apenas o desfecho de espera possui uma próxima tentativa, impedindo
estados contraditórios na interface.

Foram aplicadas as skills `implement`, `python-clean-code`, `codebase-design`, `tdd` e
`code-review`. A extração atende à separação de responsabilidades e níveis de abstração
(G6, G30 e G34), agrupa o contexto da tentativa para reduzir argumentos (F1), elimina o
flag redundante da agregação (F3/G15) e mantém estados explícitos e válidos (G26).

## Testes e verificações

O primeiro teste do novo seam falhou antes da implementação porque o módulo ainda não
existia. Depois da extração, o teste demonstra que o entregador agrega uma falha permanente,
preserva confirmações de outro destinatário e não encerra o pedido por conta própria.

Na correção dos achados do review, dois testes falharam antes das mudanças: a dispersão não
podia ser injetada e um resultado de espera sem data era aceito. Ambos passaram depois da
correção. A suíte focal do processamento passou com 70 testes.

O gate `make verificar` passou após a última alteração com Ruff, formatação, mypy e 489
testes. Permaneceram apenas avisos de depreciação de dependências já existentes.

## Code-review

A primeira rodada encontrou três problemas no eixo Standards: aleatoriedade global, um flag
redundante e um resultado que permitia combinações inválidas. Todos foram corrigidos. O eixo
Spec não encontrou desvio comportamental.

O re-review do código corrigido concluiu **Standards: OK** e **Spec: OK**, sem regressões de
segurança, idempotência, concorrência ou comportamento nos AC03, AC13, AC14 e AC32–AC35.

## Próximo passo

O ticket 29 pode usar `ResultadoDaEntrega` para encapsular o encerramento do pedido e o
avanço do ciclo, reduzindo a responsabilidade restante de `ProcessarPedido`.
