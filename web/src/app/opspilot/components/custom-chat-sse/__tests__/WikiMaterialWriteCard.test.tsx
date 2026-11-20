import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const get = vi.fn();
const post = vi.fn();

vi.mock('@/utils/request', () => ({
  default: () => ({ get, post }),
}));

vi.mock('@bk-lite/chat-content/ui', () => ({
  ChatMarkdown: ({ content }: { content: string }) => <div>{content}</div>,
}));

import WikiMaterialWriteCard from '../WikiMaterialWriteCard';

const fullIncoming = `${'新'.repeat(4001)}TAIL`;

describe('WikiMaterialWriteCard', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockResolvedValue({
      material_id: 7,
      phase: 'needs_decision',
      summary: '这条知识与已有内容冲突，请在对话里确认',
      pages: [],
      checks: [
        {
          id: 3,
          page_title: '告警规则',
          current_body: '当前规则',
          incoming_body: fullIncoming,
          actions: ['edit_accept'],
          status: 'open',
        },
      ],
    });
  });

  it('shows that the preview is shortened and edits the full candidate', async () => {
    const user = userEvent.setup();
    render(<WikiMaterialWriteCard materialId={7} phase="writing" summary="正在写入，请在此等待结果" />);

    expect(await screen.findByText('还有未展示的全文')).toBeTruthy();
    expect(screen.queryByText(fullIncoming)).toBeNull();
    expect(screen.getByText('待确认内容').parentElement?.textContent || '').not.toContain('TAIL');

    await user.click(screen.getByRole('button', { name: '编辑后采用' }));
    const draft = screen.getByRole('textbox') as HTMLTextAreaElement;
    expect(draft.value).toBe(fullIncoming);
    expect(draft.value.endsWith('TAIL')).toBe(true);

    await user.click(screen.getByRole('button', { name: '提 交' }));
    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        '/opspilot/chat_wiki_material/7/decide/',
        { check_id: 3, action: 'edit_accept', body: fullIncoming },
      );
    });
  });
});
