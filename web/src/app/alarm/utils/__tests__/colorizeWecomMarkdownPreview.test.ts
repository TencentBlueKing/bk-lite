import { colorizeWecomMarkdownPreview } from '../colorizeWecomMarkdownPreview';

describe('企微 Markdown 预览颜色', () => {
  it('只把 info、comment、warning 画成颜色', () => {
    const html = '<h3>告警分派｜&lt;font color=&quot;warning&quot;&gt;严重&lt;/font&gt;</h3>';

    expect(colorizeWecomMarkdownPreview(html)).toBe(
      '<h3>告警分派｜<span class="wecom-warning">严重</span></h3>',
    );
    expect(colorizeWecomMarkdownPreview('&lt;font color=&quot;red&quot;&gt;严重&lt;/font&gt;')).toContain('color=&quot;red&quot;');
    expect(colorizeWecomMarkdownPreview('<h3>测试发送｜&lt;font color="comment"&gt;警告&lt;/font&gt;</h3>')).toBe(
      '<h3>测试发送｜<span class="wecom-comment">警告</span></h3>',
    );
  });
});
