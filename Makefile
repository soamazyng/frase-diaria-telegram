.PHONY: instalar teste lint formatar verificar

instalar:          ## Instala as dependências travadas no uv.lock
	uv sync

teste:             ## Roda a suíte de testes
	uv run pytest

lint:              ## Análise estática: ruff (regras + formatação) e mypy estrito
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src tests

formatar:          ## Corrige o que é corrigível automaticamente
	uv run ruff check --fix .
	uv run ruff format .

verificar: lint teste   ## O que o CI vai exigir: análise estática + testes

# O SAM CLI instalado na máquina pode ser antigo demais para o runtime escolhido
# (1.125.0 não conhece python3.13). Rodar via uvx usa sempre uma versão atual,
# isolada, sem alterar a instalação global.
SAM ?= uvx --from aws-sam-cli sam

# --- Empacotamento para a AWS -------------------------------------------------
# Alvo consumido pelo SAM (Metadata: BuildMethod: makefile) de toda função
# declarada em infra/aplicacao.yaml. O pip precisa baixar wheels de
# linux/arm64: instalar no macOS traria binários de macOS e a função quebraria
# em tempo de execução, não no build.
#
# As quatro funções repetem o mesmo pacote (código único, sem dependências por
# função) — por isso uma única regra multi-alvo cobre as quatro. Faltavam
# AgendadorDiario e Reconciliador aqui (só Funcao/Worker); nunca dava erro em
# make publicar-app porque, na última vez que rodou de verdade (ticket 03), as
# duas ainda não existiam. Achado ao exercitar `make construir-app` (ticket 18)
# pela primeira vez com as quatro funções presentes — build falhava com "No
# rule to make target `build-AgendadorDiario'".
build-Funcao build-Worker build-AgendadorDiario build-Reconciliador:
	uv export --no-dev --no-emit-project --frozen --quiet -o "$(ARTIFACTS_DIR)/requirements.txt"
	uv pip install \
		--requirement "$(ARTIFACTS_DIR)/requirements.txt" \
		--target "$(ARTIFACTS_DIR)" \
		--python-platform aarch64-manylinux2014 \
		--python-version 3.13 \
		--quiet
	cp -r src/frase_diaria "$(ARTIFACTS_DIR)/"
	rm -f "$(ARTIFACTS_DIR)/requirements.txt"
	find "$(ARTIFACTS_DIR)" -name __pycache__ -type d -prune -exec rm -rf {} +
	# .lock: marcador vazio que `uv pip install --target` deixa para trás,
	# sem uso em runtime. Achado ao exercitar o pipeline de verdade (ticket
	# 18): por ser oculto, `actions/upload-artifact` o descarta por padrão
	# (`include-hidden-files: false`), então o checksum calculado antes do
	# upload (com o .lock) nunca batia com o recalculado depois do download
	# (sem ele) — a publicação era corretamente bloqueada, mas por um
	# arquivo irrelevante. Removê-lo aqui torna o artefato limpo e o
	# checksum estável nas duas pontas.
	find "$(ARTIFACTS_DIR)" -name '.lock' -type f -delete

.PHONY: publicar-dados publicar-app validar-sam construir-app publicar-app-artefato

publicar-dados:    ## Publica a stack de dados (uma vez; não muda a cada deploy)
	$(SAM) deploy --template infra/dados.yaml --stack-name frase-diaria-dados \
		--region us-east-1 --profile perfil-padrao \
		--capabilities CAPABILITY_IAM --resolve-s3 --no-fail-on-empty-changeset

publicar-app:      ## Publica a stack de aplicação (uso manual/local). VERSAO=<sha> para identificar a versão
	$(SAM) build --template infra/aplicacao.yaml
	$(SAM) deploy --stack-name frase-diaria-app \
		--region us-east-1 --profile perfil-padrao \
		--capabilities CAPABILITY_IAM --resolve-s3 --no-fail-on-empty-changeset \
		--parameter-overrides Versao=$${VERSAO:-desenvolvimento}

# --- Alvos usados pelo pipeline (ticket 18) -----------------------------------
# Build, validação e publicação separados: o pipeline constrói o artefato uma
# única vez (job "construir") e só o publica depois (job "publicar"), sem
# reconstruir — "publicar exatamente o artefato avaliado" (spec, 4.11).

validar-sam:       ## Valida infra/aplicacao.yaml (cfn-lint local; não exige credencial AWS)
	$(SAM) validate --lint --template infra/aplicacao.yaml --region us-east-1

construir-app:     ## Constrói o artefato da aplicação em .aws-sam/build, sem publicar
	$(SAM) build --template infra/aplicacao.yaml

publicar-app-artefato:   ## Publica o artefato já construído em .aws-sam/build. VERSAO=<sha> obrigatório
	$(SAM) deploy --template-file .aws-sam/build/template.yaml --stack-name frase-diaria-app \
		--region us-east-1 \
		--capabilities CAPABILITY_IAM --resolve-s3 --no-fail-on-empty-changeset \
		--parameter-overrides Versao=$${VERSAO:?defina VERSAO com o SHA publicado}
