# Renderização rica e divisão de mensagens

## Comportamento

`FonteDeFrasesNotion` transforma os trechos preservados em HTML aceito pela Bot
API. Escape de texto e atributos de links impede que caracteres do conteúdo
sejam interpretados como marcação. Negrito, itálico, tachado, sublinhado,
código e links são preservados; blocos continuam na ordem original, separados
por quebras de linha.

Uma frase continua sendo uma entrega lógica, mas agora pode resultar em várias
partes. O `RenderizadorTelegram` divide cada parte no limite configurável de
4.096 caracteres do texto da Bot API e reabre as marcações em cada fragmento,
mantendo HTML válido e sem perda de conteúdo. O cliente Telegram envia
`parse_mode=HTML`.

## Decisão técnica

A renderização fica no adaptador Telegram, depois da leitura completa do Notion:
o domínio continua armazenando conteúdo preservado e o worker continua
operando sobre `Frase` pronta para entrega. A divisão usa segmentos lógicos de
texto, contando caracteres do conteúdo e escapando somente no momento de gerar
HTML. Assim, uma tag nunca é cortada entre mensagens e a identidade, o ciclo e
o histórico do pedido permanecem inalterados.

Imagens e legendas permanecem no ticket 13; o limite de legenda não é aplicado
até existir a entrega de mídia.

## Verificação

- Skills aplicadas: `implement`, `python-clean-code` e `code-review`.
- `ruff check src tests`, `ruff format --check` e `mypy src`: OK.
- `pytest`: 279 testes passaram.
- Testes novos cobrem escape, anotações, links, ordem dos blocos, divisão e
  frases sem conteúdo textual; o contrato do canal confirma `parse_mode=HTML`.

## Review

Standards: OK; nomes, tipos, responsabilidades e constantes seguem as regras
do repositório, sem achados impeditivos.

Spec: OK para AC11; o conteúdo rico, a ordem, o escape e a divisão em partes
válidas estão cobertos. A validação específica de legendas/mídia fica
explicitamente no ticket 13.
