import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { TicketSurveyPanel } from './ticket-survey';

Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
afterEach(cleanup);

it('校验必答题并按题目标识提交', async () => {
  const submit = vi.fn().mockResolvedValue(undefined);
  render(<TicketSurveyPanel canSurvey onSubmit={submit} template={{
    name: '服务反馈', questions: [{ id: 'service', title: '恢复是否及时', required: true }],
  }} />);
  fireEvent.click(screen.getByRole('button', { name: '提交评价' }));
  expect(await screen.findByText('请填写答复')).toBeTruthy();
  expect(submit).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('恢复是否及时'), { target: { value: '及时恢复' } });
  fireEvent.click(screen.getByRole('button', { name: '提交评价' }));
  await waitFor(() => expect(submit).toHaveBeenCalledWith({ score: 5, comment: '', answers: { service: '及时恢复' } }));
});

it('使用答卷保留的题目和答案展示历史评价', () => {
  render(<TicketSurveyPanel canSurvey={false} onSubmit={vi.fn()} result={{
    score: 4, comment: '谢谢', answers: [{ id: 'service', title: '恢复是否及时', value: '及时恢复' }],
  }} />);
  expect(screen.getByText('恢复是否及时')).toBeTruthy();
  expect(screen.getByText('及时恢复')).toBeTruthy();
  expect(screen.queryByRole('button', { name: '提交评价' })).toBeNull();
});
