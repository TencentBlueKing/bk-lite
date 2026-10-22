import { describe, expect, it } from 'vitest';
import { colorizeFeishuMarkdownPreview } from '../colorizeFeishuMarkdownPreview';

describe('飞书 Markdown 预览颜色', () => {
  it('把飞书颜色标签换成可着色的文本，并保留非法颜色', () => {
    const html = '<p><strong>告警级别：</strong> &lt;font color=&#39;yellow&#39;&gt;警告&lt;/font&gt;</p>';

    expect(colorizeFeishuMarkdownPreview(html)).toBe(
      '<p><strong>告警级别：</strong> <span class="feishu-yellow">警告</span></p>',
    );
    expect(colorizeFeishuMarkdownPreview("&lt;font color='red'&gt;严重&lt;/font&gt;")).toBe(
      '<span class="feishu-red">严重</span>',
    );
    expect(colorizeFeishuMarkdownPreview('&lt;font color="warning"&gt;严重&lt;/font&gt;')).toContain('color="warning"');
  });
});
