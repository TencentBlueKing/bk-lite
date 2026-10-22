const FEISHU_FONT_TAG = /&lt;font color=(?:&quot;|&#34;|"|&#39;|&apos;|')(red|orange|yellow|green|grey|blue|turquoise|lime|carmine|violet|purple|indigo|wathet|neutral)(?:&quot;|&#34;|"|&#39;|&apos;|')&gt;([\s\S]*?)&lt;\/font&gt;/g;

export const FEISHU_MARKDOWN_PREVIEW_STYLE = [
  '.feishu-red{color:#f54a45;font-weight:600}',
  '.feishu-orange{color:#ff8800;font-weight:600}',
  '.feishu-yellow{color:#c48a00;font-weight:600}',
  '.feishu-green{color:#34c724;font-weight:600}',
  '.feishu-grey{color:#8f959e;font-weight:600}',
  '.feishu-blue{color:#3370ff;font-weight:600}',
  '.feishu-turquoise{color:#04b49c;font-weight:600}',
  '.feishu-lime{color:#7cb305;font-weight:600}',
  '.feishu-carmine{color:#f01d94;font-weight:600}',
  '.feishu-violet{color:#7b61ff;font-weight:600}',
  '.feishu-purple{color:#7a45e5;font-weight:600}',
  '.feishu-indigo{color:#4e59dd;font-weight:600}',
  '.feishu-wathet{color:#1496ff;font-weight:600}',
  '.feishu-neutral{color:#1f2329;font-weight:600}',
].join('');

export const colorizeFeishuMarkdownPreview = (html: string) => html.replace(
  FEISHU_FONT_TAG,
  (_, color: string, text: string) => `<span class="feishu-${color}">${text}</span>`,
);
