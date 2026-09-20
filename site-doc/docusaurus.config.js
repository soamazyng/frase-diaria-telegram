// @ts-check
import {themes as prismThemes} from 'prism-react-renderer';

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'Frase Diária',
  tagline: 'Uma frase por dia, direto no Telegram',
  favicon: 'img/favicon.svg',

  future: {
    v4: true,
  },

  url: 'https://soamazyng.github.io',
  baseUrl: '/frase-diaria-telegram/',

  organizationName: 'soamazyng',
  projectName: 'frase-diaria-telegram',

  onBrokenLinks: 'throw',
  markdown: {
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },

  i18n: {
    defaultLocale: 'pt-BR',
    locales: ['pt-BR'],
  },

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          sidebarPath: './sidebars.js',
          editUrl:
            'https://github.com/soamazyng/frase-diaria-telegram/tree/main/site-doc/',
          routeBasePath: 'docs',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      colorMode: {
        defaultMode: 'light',
        respectPrefersColorScheme: true,
      },
      navbar: {
        title: 'Frase Diária',
        logo: {
          alt: 'Ícone de uma citação, no estilo do bot',
          src: 'img/logo.svg',
        },
        items: [
          {
            type: 'docSidebar',
            sidebarId: 'docsSidebar',
            position: 'left',
            label: 'Documentação',
          },
          {
            href: 'https://github.com/soamazyng/frase-diaria-telegram',
            label: 'GitHub',
            position: 'right',
          },
        ],
      },
      footer: {
        style: 'dark',
        links: [
          {
            title: 'Documentação',
            items: [
              {label: 'Início', to: '/'},
              {label: 'Como funciona', to: '/docs/como-funciona'},
              {label: 'Bastidores', to: '/docs/bastidores/aprendizados-com-ia'},
            ],
          },
          {
            title: 'Projeto',
            items: [
              {
                label: 'Código-fonte no GitHub',
                href: 'https://github.com/soamazyng/frase-diaria-telegram',
              },
            ],
          },
        ],
        copyright: `Um projeto pessoal, mantido com carinho. © ${new Date().getFullYear()}.`,
      },
      prism: {
        theme: prismThemes.github,
        darkTheme: prismThemes.dracula,
      },
    }),
};

export default config;
