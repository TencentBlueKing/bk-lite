import { themes as prismThemes } from 'prism-react-renderer';

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'BlueKing Lite',
  tagline: 'AI 原生的轻量化蓝鲸平台，重塑智能运维体验',
  favicon: 'img/logo-site.png',

  future: {
    v4: true,
  },

  url: 'https://bklite.ai',
  baseUrl: '/',

  organizationName: 'BlueKing Lite',
  projectName: 'bk-lite',

  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'warn',

  i18n: {
    defaultLocale: 'zh-Hans',
    locales: ['zh-Hans', 'en'],
  },

  headTags: [
    {
      tagName: 'script',
      attributes: {},
      innerHTML: `
        var _hmt = _hmt || [];
        (function() {
          var hm = document.createElement("script");
          hm.src = "https://hm.baidu.com/hm.js?f5af2457fe2f6425e192e114ac119aff";
          var s = document.getElementsByTagName("script")[0]; 
          s.parentNode.insertBefore(hm, s);
        })();
      `,
    },
  ],

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          sidebarPath: './sidebars.js',
          editUrl:
            'https://github.com/TencentBlueKing/bk-lite',
        },
        blog: {
          showReadingTime: true,
          feedOptions: {
            type: ['rss', 'atom'],
            xslt: true,
          },
          editUrl: 'https://github.com/TencentBlueKing/bk-lite',
          onInlineTags: 'warn',
          onInlineAuthors: 'warn',
          onUntruncatedBlogPosts: 'warn',
        },
        theme: {
          customCss: './src/css/custom.css',
        },
        sitemap: {
          lastmod: 'date',
          changefreq: 'weekly',
          priority: null,
          ignorePatterns: ['/tags/**'],
          filename: 'sitemap.xml',
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      image: 'img/bklite-social-card.jpg',
      navbar: {
        title: 'BlueKing Lite',
        logo: {
          alt: 'BKLite Logo',
          src: 'img/logo-site.png',
        },
        items: [
          {
            "label": "部署指南",
            "to": "/docs/deploy/docker-compose"
          },
          {
            "label": "产品文档",
            "to": "/docs/products/opspilot/introduce"
          },
          {
            "label": "运维手册",
            "to": "#"
          },
          {
            "label": "开发指南",
            "to": "#"
          },
          {
            "label": "资源下载",
            "to": "#"
          },
          {
            "label": "FAQ",
            "to": "#"
          },
          {
            label: '在线体验',
            href: 'https://bklite.canway.net/',
            position: 'right',
          },
          {
            href: 'https://github.com/TencentBlueKing/bk-lite',
            label: 'GitHub',
            position: 'right',
          },
        ],
      },
      footer: {
        style: 'dark',
        links: [
          {
            title: '产品',
            items: [
              {
                label: '在线体验',
                href: 'https://bklite.canway.net/',
              },
              {
                label: '部署指南',
                to: '/docs/deploy/docker-compose',
              }
            ],
          },
          {
            title: '社区',
            items: [
              {
                label: '腾讯蓝鲸',
                href: 'https://bk.tencent.com/',
              },
              {
                label: 'GitHub',
                href: 'https://github.com/TencentBlueKing/bk-lite',
              },
            ],
          },
          {
            title: '更多',
            items: [
              {
                label: '开源协议',
                href: 'https://github.com/TencentBlueKing/bk-lite/blob/master/LICENSE.txt',
              },
            ],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} BlueKing Lite.`,
      },
      colorMode: {
        defaultMode: 'light',
        disableSwitch: true,
        respectPrefersColorScheme: false,
      },
      prism: {
        theme: prismThemes.github,
        darkTheme: prismThemes.dracula,
      },
    }),
};

export default config;
