// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  docsSidebar: [
    {
      type: 'category',
      label: 'Produto',
      collapsible: false,
      items: [
        'como-funciona',
        'a-colecao',
        'frases-em-destaque',
        'compartilhar-com-quem-voce-ama',
      ],
    },
    {
      type: 'category',
      label: 'Bastidores',
      collapsible: false,
      items: [
        'bastidores/aprendizados-com-ia',
        'bastidores/infraestrutura-e-gasto-zero',
        'bastidores/cicd-e-publicacao',
      ],
    },
  ],
};

export default sidebars;
