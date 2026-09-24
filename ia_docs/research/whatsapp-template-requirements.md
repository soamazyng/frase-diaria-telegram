# Pesquisa: requisitos de template de mensagem da WhatsApp Cloud API para envio proativo diário

Data da pesquisa: 2026-09-24

## Resumo executivo

O envio diário às 8h é, por definição, uma mensagem iniciada pela empresa fora da janela de atendimento de 24h — a documentação da Meta confirma que, fora dessa janela, **só mensagens de template pré-aprovado podem ser enviadas** (developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages, acesso 2026-09-24). Existem hoje exatamente três categorias de template — **Marketing**, **Utility** e **Authentication** — e, pela definição oficial de "utility" (não-promocional **e** específico à conta/transação do usuário ou crítico à segurança), uma frase motivacional diária recorrente **não se encaixa em utility** e tenderia a ser classificada como **marketing**, o que tem implicações de custo/qualidade que a spec do projeto ainda não havia considerado. O corpo (body) do template aceita até 1024 caracteres, parâmetros nomeados ou posicionais, mas a documentação oficial **não menciona suporte a formatação estilo WhatsApp (negrito/itálico/riscado/monospace)** dentro do template — o header de texto, inclusive, é instruído a **não usar caracteres de Markdown**. A revisão combina sistemas automatizados e humanos, com decisão em até 24h. Sobre o número de teste: a documentação oficial **não descreve diferenças no processo/prazo de aprovação de template** entre número de teste e número de produção — a única diferença documentada está nos limites de envio e na dispensa de forma de pagamento. Templates são recursos da **WhatsApp Business Account (WABA)**, não do número de telefone (confirmado pelo endpoint `POST /{WABA-ID}/message_templates` e pelo limite de "250 templates por WABA"), o que sugere fortemente que um template aprovado enquanto se usa o número de teste continua válido ao adicionar um número de produção à mesma WABA — mas a Meta **não faz essa afirmação de forma explícita** em nenhuma página consultada; é uma inferência estrutural, não um fato documentado.

---

## 1. Categorias de template

A Meta define hoje exatamente três categorias, sem indício de uma quarta categoria ou de renomeação recente além da introdução deste esquema em junho de 2023:

- **Marketing** — "enable businesses to achieve a wide range of goals, from generating awareness to driving sales and retargeting customers." Inclui conteúdo misto e qualquer template cujo conteúdo não se encaixe claramente em utility/authentication.
  Fonte: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-categorization (acesso 2026-09-24)

- **Utility** — "enable businesses to follow up on user actions or requests, since these messages are typically triggered by user actions." Para ser classificado como utility, o template precisa satisfazer **as duas** condições:
  1. Ser "non-promotional, not containing any promotional or persuasive intent";
  2. Ser "specific to or requested by the user (clearly related to their order, account, services, or transactions)" **ou** ser "essential or critical to the user" (relacionado à segurança).
  Exemplos típicos: confirmação de pedido, alerta de conta, pesquisa de satisfação atrelada a uma transação específica.
  Fonte: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-categorization (acesso 2026-09-24); também https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/utility-templates/utility-templates (acesso 2026-09-24, não lida na íntegra nesta pesquisa, apenas indexada na busca).

- **Authentication** — restrito a "one-time passcodes for identity verification" em etapas como criação de conta, recuperação de acesso ou confirmação de transação. Exige uso da biblioteca de templates de autenticação do Cloud API, botão de código (copy-code ou one-tap), e tem restrições fortes de conteúdo: sem URLs, sem mídia, sem emojis, parâmetros limitados a 15 caracteres.
  Fonte: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-categorization (acesso 2026-09-24); https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/authentication-templates/authentication-templates/ (acesso 2026-09-24, indexada mas não lida na íntegra).

**Quem decide a categoria:** o desenvolvedor declara a categoria pretendida ao criar o template, e a Meta valida/pode corrigir: "When you create a template, you indicate the template's category based on the guidelines, and WhatsApp validates the category you indicated per the contents of the template and the guidelines." A Meta pode rejeitar ou reclassificar automaticamente um template cuja categoria declarada não bate com o conteúdo.
Fonte: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-categorization (acesso 2026-09-24)

**Aplicação ao caso do projeto (frase diária motivacional):** o envio diário é recorrente, não é disparado por uma ação/pedido do usuário no momento do envio, e seu conteúdo (uma frase motivacional) tem intenção mais próxima de "engajamento/relacionamento" do que de "atualização transacional". Isso não bate com o requisito "specific to or requested by the user... related to their order, account, services, or transactions" da categoria utility. A categoria que melhor se encaixa, pela definição textual da Meta, é **marketing** — embora a documentação não tenha um exemplo literal de "frase motivacional diária" para confirmar isso com 100% de certeza; é uma inferência a partir da definição, não uma citação direta da Meta sobre este caso específico.

---

## 2. Estrutura de um template

Fonte principal desta seção: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/components/ (acesso 2026-09-24)

### Componentes

- **Header (opcional, no máximo 1 por template):**
  - Texto: aceita 1 parâmetro, máximo 60 caracteres, e a documentação instrui a **não usar caracteres especiais de Markdown** no header de texto.
  - Mídia: IMAGE, VIDEO, GIF ou DOCUMENT, enviados via Resumable Upload API (GIFs como mp4, até 3.5MB).
  - Location: exibe mapa (latitude/longitude/nome/endereço), usado em casos de entrega/rastreamento.

- **Body (obrigatório, único por template):**
  - "The message text in the body component accepts multiple parameters."
  - **Limite de caracteres: 1024 caracteres.**
  - Aceita parâmetros nomeados ou posicionais (ver abaixo).
  - A documentação consultada **não menciona suporte a formatação estilo WhatsApp** (negrito `*texto*`, itálico `_texto_`, riscado `~texto~`, monospace `` ```texto``` ``) dentro do corpo do template — nenhuma das páginas de componentes ou de criação de template consultadas confirma ou nega explicitamente essa formatação no body. Dado que o header de texto é instruído a evitar Markdown, e nenhuma página menciona a formatação como recurso do body, o estado documentado é de **lacuna** — não uma negação explícita, mas também não uma confirmação. (Ver seção "Perguntas em aberto".)

- **Footer (opcional, único por template):**
  - Texto apenas, sem parâmetros.
  - **Limite de caracteres: 60.**

- **Buttons (opcional, até 10 por template no total):**
  - Quick Reply: até 10, apenas texto.
  - URL: até 2, com suporte a 1 variável.
  - Phone Number: até 1.
  - Copy Code: até 1, máx. 20 caracteres.
  - Também existem botões de Voice Call, SPM (single product message) e multi-product, conforme o tipo de template.
  - Nota de UX: "templates composed of 4 or more buttons...cannot be viewed on WhatsApp desktop clients."

### Parâmetros variáveis

A Meta hoje suporta dois formatos de parâmetro (confirmado em https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview, acesso 2026-09-24):

- **Nomeados** (formato mais novo): `{{first_name}}` — "Parameters using the named format must be unique, single strings, composed of lowercase characters and underscores, wrapped in double curly brackets."
- **Posicionais** (formato clássico): `{{1}}`, `{{2}}` — "Positional parameters must be ordered array index numbers, starting from 1, wrapped in double curly brackets."

Ou seja: a Meta **não substituiu** o formato `{{1}}` — os dois formatos coexistem hoje, e o desenvolvedor escolhe um ao criar o template.

---

## 3. Processo de aprovação

Fonte: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-review (acesso 2026-09-24)

- **Quem revisa:** combinação de sistemas automatizados e revisão manual — "the content undergoes validation through a combination of automated systems and manual reviews." A documentação não detalha o critério exato de quando um template escala para revisão humana.
- **Prazo:** "It can take up to 24 hours for an approval decision to be made." Após aprovação, o template entra em estado "Active - Quality pending" (a qualidade real do template só é calculada depois de uso real).
- **Notificação:** via WhatsApp Manager, e-mail e webhooks.
- **Motivos comuns de rejeição documentados pela Meta**, agrupados:
  - **Formatação de parâmetros:** parâmetros mal formatados (deveriam ser `{{1}}`), uso de caracteres especiais (`#`, `$`, `%`) dentro de parâmetros, numeração não sequencial, excesso de parâmetros em relação ao tamanho da mensagem, parâmetros no início/fim da mensagem.
  - **Violação de política:** descumprimento de requisitos da Política de Comércio para divulgação de transações, solicitação de identificadores sensíveis (números completos de cartão/conta, documentos nacionais), conteúdo "potentially abusive or threatening" (ex.: ameaça de ação legal ao cliente).
  - **Problemas técnicos:** violação de limite de caracteres conforme formatação/tags, restrição de quantidade de emojis, templates duplicados com corpo e rodapé idênticos.
  - **Descompasso de categoria:** quando o conteúdo não corresponde à categoria declarada (ex.: declarar "utility" mas escrever um discurso de vendas) — a Meta pode rejeitar ou reclassificar.
- **Recurso (appeal):** templates rejeitados podem ser contestados em até 24h, exigindo reenvio com valores de exemplo e ativos de mídia.

---

## 4. Modo de número de teste

Fontes consultadas:
- https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started (acesso 2026-09-24)
- https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform (acesso 2026-09-24)
- https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits (acesso 2026-09-24)

**O que a documentação confirma sobre o número de teste:**
- Ao concluir o fluxo "Get Started" do Cloud API, uma WABA de teste e um número de telefone de teste são criados automaticamente: "a test WhatsApp Business account and test business phone number are automatically created for you."
- Números de teste têm "relaxed messaging limits and don't require a payment method on file in order to send template messages."
- Um template pré-aprovado chamado "hello world" já vem disponível para começar a testar imediatamente, sem esperar aprovação: "for testing purposes, a pre-approved 'hello world' template is created automatically to help you get started."
- Busca complementar (não verificada em página primária lida por inteiro, mas indexada em resultado de busca sobre o Cloud API) indica que o número de teste permite enviar mensagens para **até 5 números de destinatário**, cada um precisando ser verificado por código de confirmação enviado via WhatsApp — porém eu não consegui abrir a página primária específica que declara esse limite de "5" com uma citação literal; ele apareceu apenas via resumo de busca, não via WebFetch de uma URL developers.facebook.com. Tratar esse número "5" como **não confirmado por citação direta nesta pesquisa**, apesar de ser uma informação amplamente replicada.

**O que a documentação NÃO confirma (lacuna relevante para a pergunta 4):**
- Nenhuma das páginas oficiais lidas (`get-started`, `about-the-platform`, `messaging-limits`, `template-review`) menciona **qualquer diferença no processo de aprovação de template ou no prazo de aprovação** entre um número em modo de teste e um número de produção verificado. A página de revisão de template (`template-review`) não distingue o cenário "WABA em modo teste" do cenário "WABA de produção" em nenhum momento.
- Ou seja: pela documentação primária disponível, **o processo de submissão e aprovação de template parece ser o mesmo independentemente do número estar em modo teste** — a única diferença documentada entre os dois modos está nos **limites de envio de mensagem** e na **dispensa de forma de pagamento**, não no fluxo de aprovação do template em si. Isso é uma leitura por ausência de evidência em contrário, não uma afirmação positiva da Meta de que "o processo é idêntico" — ver seção de perguntas em aberto.

---

## 5. Migração futura (número de teste → número de produção)

Este é o ponto onde a documentação primária da Meta é mais escassa. Registro aqui exatamente o que é fato documentado, o que é inferência estrutural, e o que é fonte secundária.

### Fato documentado diretamente

- Templates são criados, listados e apagados por um endpoint que usa o **ID da WABA**, não o ID do número de telefone: `POST /{Version}/{WABA-ID}/message_templates`, `GET /{Version}/{WABA-ID}/message_templates`, `DELETE /{Version}/{WABA-ID}/message_templates`.
  Fonte: https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/whatsapp-business-account/template-api (acesso 2026-09-24)
- O limite de quantidade de templates é contado por WABA, não por número: "A WhatsApp Business account (WABA) can have a maximum of 250 message templates" (ou até 6.000 se o negócio-pai for verificado e ao menos um número da WABA tiver display name aprovado).
  Fonte: indexada via busca a partir de developers.facebook.com/documentation/business-messaging/whatsapp/templates (não confirmada por WebFetch direto de uma única página; tratar como fato de alta confiança dado que bate com o endpoint acima, mas não citada literalmente de uma página primária aberta nesta pesquisa).

### Inferência estrutural (não é uma afirmação direta da Meta)

Como o template pertence à WABA e não ao número de telefone, a leitura estrutural mais razoável é que **um template aprovado enquanto a WABA está associada só a um número de teste continua sendo um recurso da mesma WABA quando um número de produção é adicionado a ela** — ou seja, o template não "pertence" ao número de teste e não deveria precisar de nova aprovação ao trocar/adicionar o número. **Isto não é uma citação da Meta; é dedução a partir do modelo de dados documentado (WABA-scoped).**

### O que a Meta explicitamente NÃO diz (lacuna confirmada)

- Nenhuma das páginas oficiais lidas nesta pesquisa (`get-started`, `about-the-platform`, `whatsapp-business-accounts`, `business-phone-numbers/phone-numbers`, `template-review`, `template-api`) contém uma frase que afirme diretamente "templates aprovados em modo de teste permanecem aprovados ao migrar para um número de produção" ou o contrário. A página `about-the-platform` foi verificada especificamente para esse propósito e retornou: "does not contain specific guidance on migrating from test phone numbers to production phone numbers. It only describes how to delete test resources entirely through the App Dashboard."
- A página `whatsapp-business-accounts` também não confirma explicitamente se templates são compartilhados entre múltiplos números da mesma WABA — apenas o limite de "250 templates por WABA" aponta nessa direção.

### Fonte secundária (não é Meta, tratar como não confirmado)

- Resultados de busca sobre "migração de número" na Cloud API (ex.: respond.io, bolddesk — **fontes secundárias de provedores/BSPs, não Meta**) descrevem um cenário diferente do perguntado aqui: a migração de um número **já em produção** de um BSP terceiro para o Cloud API da própria Meta, preservando templates aprovados, display name, quality rating e limites de envio. Esse cenário (migração de BSP) **não é o mesmo** que "sair do modo de número de teste para um número de produção dentro do Cloud API", e não deve ser citado como resposta à pergunta 5. Marcar claramente: **fonte secundária, cenário diferente do perguntado, não usar como fato confirmado pela Meta sobre número de teste.**

**Conclusão da pergunta 5:** a Meta não faz, nas páginas oficiais consultadas, uma afirmação explícita sobre a validade de um template aprovado em modo de teste após a migração para um número de produção. Existe um indício estrutural forte (template pertence à WABA, não ao número) que sugere continuidade, mas isso é inferência do agente de pesquisa, não fato citável da Meta.

---

## Perguntas em aberto / fog

1. **Formatação de texto (negrito/itálico/riscado/monospace) no body do template:** nenhuma página oficial consultada confirma ou nega explicitamente que o corpo do template aceita a sintaxe de formatação do WhatsApp (`*texto*`, `_texto_`, `~texto~`, `` ```texto``` ``). O header de texto é instruído a **evitar** Markdown, o que é um indício indireto, mas não uma resposta direta sobre o body. Recomendo teste empírico manual (criar um template de teste com `*negrito*` no body e observar se a Meta rejeita, ignora ou renderiza) antes de assumir qualquer comportamento.
2. **Limite de "5 números de destinatário" em modo de teste:** amplamente citado em buscas, mas não confirmado por uma citação literal de uma página `developers.facebook.com` aberta diretamente nesta pesquisa. Vale reconfirmar lendo a página de "Get Started" na íntegra (passo a passo de adicionar números de destino) antes de depender desse número no desenho da solução.
3. **Processo de aprovação de template em modo de teste vs. produção:** a ausência de menção a diferenças não é o mesmo que uma confirmação de que são idênticos. Não há uma frase da Meta do tipo "templates seguem o mesmo processo de revisão independentemente do modo do número" — é uma leitura por ausência de evidência em contrário.
4. **Validade de template ao migrar de número de teste para número de produção:** ponto mais nebuloso de toda a pesquisa (ver seção 5 acima). Só há inferência estrutural (WABA-scoped), nenhuma afirmação direta da Meta. Se essa migração for relevante ao roadmap do projeto, recomendo abrir um teste controlado (criar WABA de teste, aprovar um template real com categoria "marketing", depois adicionar um número de produção verificado à mesma WABA) e observar o comportamento real, já que a documentação não fecha essa lacuna.
5. **Categoria exata para "frase motivacional diária":** a classificação em "marketing" é uma inferência a partir da definição textual de "utility" (que exige vínculo com pedido/conta/transação específica do usuário), não uma citação da Meta sobre este caso de uso específico. Não há exemplo oficial de "mensagem motivacional recorrente" nas páginas de categorização consultadas.
6. **Confirmação por citação literal do limite de 250/6.000 templates por WABA:** essa informação veio de um resumo de busca sobre a documentação de templates, não de uma leitura direta de uma URL `developers.facebook.com` única nesta sessão — vale reconfirmar a página exata antes de citar esse número como definitivo em outro documento.
