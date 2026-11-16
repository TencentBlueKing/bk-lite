import { describe, expect, it } from 'vitest';

import { argsWithResolvedKeywords, renderToolCallCard } from '../toolCallRenderer';

describe('argsWithResolvedKeywords', () => {
  const args = JSON.stringify({ status: 'active', page: 1, page_size: 20 });

  it('copies searched keywords into the displayed parameters', () => {
    const shown = argsWithResolvedKeywords(
      args,
      JSON.stringify({ success: true, searched_keywords: ['下我'] }),
    );
    expect(JSON.parse(shown)).toEqual({
      status: 'active',
      page: 1,
      page_size: 20,
      keywords: ['下我'],
    });
  });

  it('leaves parameters unchanged when the result has no keyword filter', () => {
    const result = JSON.stringify({ success: true, data: { count: 3 } });
    expect(argsWithResolvedKeywords(args, result)).toBe(args);
  });

  it('renders the resolved keywords in the parameter block', () => {
    const html = renderToolCallCard('call-1', {
      name: 'alerts_list_alerts',
      args,
      status: 'completed',
      result: JSON.stringify({
        success: true,
        data: { count: 0, items: [] },
        searched_keywords: ['下我'],
      }),
    });
    const paramsAt = html.indexOf('参数:');
    const resultAt = html.indexOf('结果:');
    expect(html.slice(paramsAt, resultAt)).toContain('下我');
  });
});
