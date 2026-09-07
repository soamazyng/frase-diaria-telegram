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
