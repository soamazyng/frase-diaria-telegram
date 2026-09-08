"""Ponto de entrada da Lambda para o tráfego HTTP.

Premissa desta configuração: API Gateway **HTTP API** com o stage `$default`, que
não prefixa o caminho. Se o ticket 03 declarar uma REST API (stage `Prod`), o
caminho chega como `/Prod/health`, o FastAPI só conhece `/health`, e a verificação
pós-publicação falha com 404 por roteamento — não por saúde. Nesse caso, passe
`api_gateway_base_path` ao Mangum.
"""

from mangum import Mangum

from frase_diaria.infraestrutura.composicao import ReceberComandoPreguicoso
from frase_diaria.infraestrutura.http.aplicacao_web import criar_aplicacao

handler = Mangum(criar_aplicacao(receber_comando=ReceberComandoPreguicoso()))
