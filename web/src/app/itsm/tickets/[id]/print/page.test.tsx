import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import TicketPrintPage from './page';

const api = vi.hoisted(() => ({ ready: true, getTicketPrint: vi.fn() }));
vi.mock('../../../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('next/navigation', () => ({ useParams: () => ({ id: '42' }), useRouter: () => ({ push: vi.fn() }) }));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it('进入页面后预览全部字段，并直接打印该预览', async () => {
  api.getTicketPrint.mockResolvedValue({
    html: '<h1>采购申请</h1><table><tr><th>申请金额</th><td>360</td></tr></table>',
    templates: [{ id: 1, name: '旧模板' }],
  });
  render(<TicketPrintPage />);

  const frame = await screen.findByTitle<HTMLIFrameElement>('工单打印预览');
  const button = screen.getByRole<HTMLButtonElement>('button', { name: /打\s*印/ });
  expect(api.getTicketPrint).toHaveBeenCalledWith(42);
  expect(frame.getAttribute('srcdoc')).toContain('<th>申请金额</th><td>360</td>');
  expect(screen.queryByRole('combobox', { name: '打印模板' })).toBeNull();
  expect(button.disabled).toBe(true);

  const print = vi.spyOn(frame.contentWindow!, 'print').mockImplementation(() => undefined);
  fireEvent.load(frame);
  expect(button.disabled).toBe(false);
  fireEvent.click(button);
  expect(print).toHaveBeenCalledOnce();
});
