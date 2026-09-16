import re
from pathlib import Path

RAIZ = Path(__file__).parents[2]


def _ler(caminho: str) -> str:
    return (RAIZ / caminho).read_text()


def test_jobs_privilegiados_usam_environment_e_arns_fora_do_git() -> None:
    publicar = _ler(".github/workflows/pr-develop-main.yml")
    reconciliar = _ler(".github/workflows/reconciliador.yml")

    assert "environment: producao" in publicar
    assert "role-to-assume: ${{ vars.AWS_ROLE_PUBLICACAO_ARN }}" in publicar
    assert "environment: producao" in reconciliar
    assert "role-to-assume: ${{ vars.AWS_ROLE_RECONCILIACAO_ARN }}" in reconciliar
    assert re.search(r"arn:aws:iam::\d{12}", publicar + reconciliar) is None


def test_artefato_tem_arquivo_duravel_e_fallback_de_recuperacao() -> None:
    publicar = _ler(".github/workflows/pr-develop-main.yml")
    reconciliar = _ler(".github/workflows/reconciliador.yml")
    obter = _ler(".github/actions/obter-artefato/action.yml")

    assert "Preservar artefato imutável para recuperação" in publicar
    assert 'chave="recuperacao/$GITHUB_REPOSITORY_ID/$GITHUB_SHA.zip"' in publicar
    assert "--if-none-match '*'" in publicar
    assert "uses: ./.github/actions/obter-artefato" in publicar
    assert "uses: ./.github/actions/obter-artefato" in reconciliar
    assert "mask-aws-account-id: true" in publicar
    assert "mask-aws-account-id: true" in reconciliar
    assert 'checksumCalculado" != "$CHECKSUM_ESPERADO' in obter
    assert "2>/dev/null" in obter


def test_bootstrap_exige_parametros_operacionais_e_claims_exatos() -> None:
    bootstrap = _ler("infra/bootstrap.yaml")

    for parametro in (
        "ProprietarioGitHub",
        "IdDoProprietarioGitHub",
        "NomeDoRepositorio",
        "IdDoRepositorio",
        "BucketGerenciadoPeloSAM",
    ):
        bloco = bootstrap.split(f"  {parametro}:\n", 1)[1].split("\n  ", 1)[0]
        assert "Default:" not in bloco
    assert "environment:${AmbienteGitHub}" in bootstrap
    assert "token.actions.githubusercontent.com:ref:" in bootstrap
    assert "apigateway:TagResource" not in bootstrap
    assert "BucketDeRecuperacao:" in bootstrap
    assert "VersioningConfiguration:" in bootstrap
    assert "DeletionPolicy: Retain" in bootstrap


def test_lambdas_nao_podem_enumerar_o_prefixo_de_parametros() -> None:
    aplicacao = _ler("infra/aplicacao.yaml")

    assert "ssm:GetParametersByPath" not in aplicacao
    assert "ssm:GetParameters" not in aplicacao
    assert "parameter/${Prefixo}/*" not in aplicacao
    assert aplicacao.count("Action: ssm:GetParameter") == 3
