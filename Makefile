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
# Alvo consumido pelo SAM (Metadata: BuildMethod: makefile) do recurso "Funcao".
# O pip precisa baixar wheels de linux/arm64: instalar no macOS traria binários
# de macOS e a função quebraria em tempo de execução, não no build.
build-Funcao build-Worker:
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

.PHONY: publicar-dados publicar-app

publicar-dados:    ## Publica a stack de dados (uma vez; não muda a cada deploy)
	$(SAM) deploy --template infra/dados.yaml --stack-name frase-diaria-dados \
		--region us-east-1 --profile perfil-padrao \
		--capabilities CAPABILITY_IAM --resolve-s3 --no-fail-on-empty-changeset

publicar-app:      ## Publica a stack de aplicação. VERSAO=<sha> para identificar a versão
	$(SAM) build --template infra/aplicacao.yaml
	$(SAM) deploy --stack-name frase-diaria-app \
		--region us-east-1 --profile perfil-padrao \
		--capabilities CAPABILITY_IAM --resolve-s3 --no-fail-on-empty-changeset \
		--parameter-overrides Versao=$${VERSAO:-desenvolvimento}
