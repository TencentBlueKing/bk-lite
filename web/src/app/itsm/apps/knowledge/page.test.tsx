import { renderItsm as render } from '../../test-utils';
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { Modal } from 'antd';
import { afterEach, expect, it, vi } from 'vitest';
import Page from './page';

const api = vi.hoisted(() => ({
  isLoading: false,
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
}));

vi.mock('@/utils/request', () => ({ default: () => api }));
vi.mock('@/theme', () => ({ useThemeMode: () => ({ mode: 'light' }) }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
afterEach(() => { Modal.destroyAll(); cleanup(); vi.clearAllMocks(); vi.restoreAllMocks(); });

const article = { id: 1, title: '值班手册', content: '<img src=invalid>\n操作步骤', status: 'published', updated_at: '2026-11-20T01:00:00Z' };
const articlesPath = '/itsm/api/resources/knowledge';

it('只读用户可安全阅读正文，且没有修改和发布按钮', async () => {
  api.get.mockResolvedValueOnce({ items: [article], count: 1 }).mockResolvedValueOnce(article);
  render(<Page />);
  fireEvent.click(await screen.findByRole('button', { name: '值班手册' }));
  const content = await screen.findByText('<img src=invalid> 操作步骤', { exact: false });
  expect(content.querySelector('img')).toBeNull();
  expect(screen.queryByRole('button', { name: '新建' })).toBeNull();
  expect(screen.queryByRole('button', { name: '编辑' })).toBeNull();
});

it('阅读富文本时保留格式并过滤可执行链接和属性', async () => {
  api.get.mockResolvedValueOnce({ items: [article], count: 1 }).mockResolvedValueOnce({
    ...article, content_format: 'richtext', content: '<p><strong>处理步骤</strong><a href="javascript:void(0)">链接</a><img src="/test.png" onerror="void(0)"></p>',
  });
  render(<Page />);
  fireEvent.click(await screen.findByRole('button', { name: '值班手册' }));
  const formatted = await screen.findByText('处理步骤');
  expect(formatted.tagName).toBe('STRONG');
  expect(screen.getByText('链接').hasAttribute('href')).toBe(false);
  expect(formatted.parentElement?.querySelector('img')?.hasAttribute('onerror')).toBe(false);
});

it('保存 Markdown 草稿的分类和关联工单', async () => {
  api.get.mockImplementation((path: string) => Promise.resolve(path === '/itsm/api/tickets'
    ? { items: [{ id: 7, sn: 'REQ-0007', title: '数据库扩容' }] }
    : { items: [], count: 0, can_add: true, can_edit: true, can_link_tickets: true, categories: ['运维'] }));
  api.post.mockResolvedValue(article);
  render(<Page />);
  fireEvent.click(await screen.findByRole('button', { name: '新建' }));
  fireEvent.change(screen.getByLabelText('标题'), { target: { value: '新增文章' } });
  fireEvent.change(screen.getByLabelText('分类'), { target: { value: '运维' } });
  fireEvent.click(screen.getByText('Markdown', { exact: true }));
  fireEvent.change(screen.getByLabelText('正文'), { target: { value: '**步骤说明**' } });
  fireEvent.click(screen.getByRole('button', { name: '预览' }));
  expect((await screen.findByText('步骤说明')).tagName).toBe('STRONG');
  const tickets = screen.getByRole('combobox', { name: '关联工单' });
  fireEvent.mouseDown(tickets);
  fireEvent.change(tickets, { target: { value: 'REQ-0007' } });
  fireEvent.click(await screen.findByText('数据库扩容'));
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith(articlesPath, {
    title: '新增文章', category: '运维', content: '**步骤说明**', content_format: 'markdown', ticket_ids: [7],
  }, expect.anything()));
});

it('附件上传失败时保留原草稿和附件，重试沿用已保存的文章', async () => {
  api.get.mockResolvedValue({ items: [], count: 0, can_add: true });
  api.post.mockImplementation((path: string) => Promise.resolve(path === articlesPath
    ? { ...article, can_upload: true, attachments: [] }
    : { id: 8, name: '步骤.md', size: 5, can_delete: true }));
  api.post.mockResolvedValueOnce({ ...article, can_upload: true, attachments: [] })
    .mockRejectedValueOnce(new Error('存储暂不可用'));
  const { container } = render(<Page />);
  fireEvent.click(await screen.findByRole('button', { name: '新建' }));
  fireEvent.change(screen.getByLabelText('标题'), { target: { value: '恢复步骤' } });
  fireEvent.change(container.ownerDocument.querySelector('input[name="file"]')!, {
    target: { files: [new File(['hello'], '步骤.md', { type: 'text/markdown' })] },
  });
  expect(await screen.findByText('步骤.md')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  expect(await screen.findByText(/存储暂不可用/)).toBeTruthy();
  expect(screen.getByText('步骤.md')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() => expect(api.post.mock.calls.map(([path]) => path)).toEqual([
    articlesPath, '/itsm/api/knowledge/1/attachments', '/itsm/api/knowledge/1/attachments',
  ]));
  expect(api.put).not.toHaveBeenCalled();
});

it.each([false, true])('已删除的附件不参与表单变更判断，文章是否被改动 %s', async (changed) => {
  api.get.mockResolvedValueOnce({ items: [article], count: 1, can_edit: true }).mockResolvedValueOnce({
    ...article, attachments: [{ id: 9, name: '附件.md', can_delete: true }],
  });
  api.del.mockResolvedValueOnce({});
  const confirmLeave = vi.spyOn(Modal, 'confirm').mockReturnValue({ destroy: vi.fn(), update: vi.fn() });
  render(<Page />);
  fireEvent.click(await screen.findByRole('button', { name: '编辑' }));
  if (changed) fireEvent.change(await screen.findByLabelText('标题'), { target: { value: '已变更标题' } });
  fireEvent.click(await screen.findByRole('button', { name: '删除附件 附件.md' }));
  fireEvent.click(screen.getByRole('button', { name: /^删\s*除$/ }));
  await waitFor(() => expect(screen.queryByText('附件.md')).toBeNull());
  fireEvent.click(screen.getByRole('button', { name: 'Close' }));

  if (changed) {
    expect(confirmLeave).toHaveBeenCalledWith(expect.objectContaining({ title: '放弃未保存的修改？' }));
    expect(screen.getByLabelText('标题')).toHaveProperty('value', '已变更标题');
  } else {
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(confirmLeave).not.toHaveBeenCalled();
  }
});

it('英文界面显示本地化的文章列和编辑文案', async () => {
  api.get.mockResolvedValueOnce({ items: [article], count: 1, can_edit: true }).mockResolvedValueOnce(article);
  render(<Page />, { locale: 'en' });
  expect(await screen.findByRole('columnheader', { name: 'Article title' })).toBeTruthy();
  fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
  expect(await screen.findByLabelText('Title')).toHaveProperty('value', article.title);
  expect(screen.getByRole('button', { name: 'Save' })).toBeTruthy();
});
