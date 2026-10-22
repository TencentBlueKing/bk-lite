const WECOM_FONT_TAG = /&lt;font color=(?:&quot;|&#34;|")(info|comment|warning)(?:&quot;|&#34;|")&gt;([\s\S]*?)&lt;\/font&gt;/g;

export const WECOM_MARKDOWN_PREVIEW_STYLE = [
  '.wecom-info{color:#1aad19;font-weight:600}',
  '.wecom-comment{color:#8c8c8c;font-weight:600}',
  '.wecom-warning{color:#ed6a0c;font-weight:600}',
].join('');

export const colorizeWecomMarkdownPreview = (html: string) => html.replace(
  WECOM_FONT_TAG,
  (_, color: string, text: string) => `<span class="wecom-${color}">${text}</span>`,
);
