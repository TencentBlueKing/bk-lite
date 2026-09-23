import { sanitizeReplayEvent } from './replay-privacy';
import { describe, expect, it } from 'vitest';

describe('Replay browser privacy boundary', () => {
  it('keeps ordinary interface text readable while masking input mutations', () => {
    const snapshot = sanitizeReplayEvent({
      type: 2,
      timestamp: 1,
      data: {
        initialOffset: { top: 0, left: 0 },
        node: {
          type: 0,
          id: 1,
          childNodes: [
            {
              type: 2,
              id: 2,
              tagName: 'nav',
              attributes: { class: 'main-menu' },
              childNodes: [{ type: 3, id: 3, textContent: '会话回放' }],
            },
          ],
        },
      },
    });
    const textMutation = sanitizeReplayEvent({
      type: 3,
      timestamp: 2,
      data: {
        source: 0,
        texts: [
          { id: 3, value: '错误详情：https://docs.example.test/errors' },
          {
            id: 5,
            value: '.avatar{background:u\\72l(https://egress.invalid/a.png)}',
          },
        ],
        attributes: [],
        removes: [],
        adds: [],
      },
    });
    const inputMutation = sanitizeReplayEvent({
      type: 3,
      timestamp: 3,
      data: {
        source: 5,
        id: 4,
        text: 'customer-input-secret',
        isChecked: false,
      },
    });

    expect(JSON.stringify(snapshot)).toContain('会话回放');
    expect(textMutation).toMatchObject({
      data: {
        texts: [
          { id: 3, value: '错误详情：https://docs.example.test/errors' },
          { id: 5, value: '[redacted]' },
        ],
      },
    });
    expect(inputMutation).toMatchObject({
      data: { source: 5, id: 4, text: '[redacted]', isChecked: false },
    });
  });
});
