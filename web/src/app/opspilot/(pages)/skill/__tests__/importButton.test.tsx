import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import SkillPage from '../page';

const granted = vi.hoisted(() => ({ values: ['Add'] }));
const push = vi.hoisted(() => vi.fn());
const importAgent = vi.hoisted(() => vi.fn());

vi.mock('@/app/opspilot/api/skill', () => ({
  useSkillApi: () => ({
    togglePin: vi.fn(),
    exportAgent: vi.fn(),
    importAgent,
  }),
}));
vi.mock('@/utils/request', () => ({
  default: () => ({
    get: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    post: vi.fn(),
    patch: vi.fn(),
    del: vi.fn(),
  }),
}));
vi.mock('@/console-layout', () => ({ useScreenAwareRouter: () => ({ push }) }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/opspilot/components/skill/SkillViewSwitcher', () => ({ default: () => null }));
vi.mock('@/app/opspilot/components/generic-modify-modal', () => ({ default: () => null }));
vi.mock('@/hooks/usePermissions', () => ({
  default: () => ({
    hasPermission: (required: string[]) => required.every((item) => granted.values.includes(item)),
  }),
}));

beforeEach(() => {
  granted.values = ['Add'];
  push.mockReset();
  importAgent.mockReset();
  window.matchMedia = vi.fn().mockImplementation(() => ({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} });
});

afterEach(() => {
  cleanup();
});

function disabledOpacity(element: HTMLElement) {
  let current: HTMLElement | null = element;
  while (current) {
    if (current.style.opacity === '0.5') {
      return true;
    }
    current = current.parentElement;
  }
  return false;
}

it('places import beside new and follows the add permission', () => {
  render(<SkillPage />);
  const importButton = screen.getByRole('button', { name: /common\.import/ });
  const newButton = screen.getByRole('button', { name: /common\.new/ });
  expect(importButton.querySelector('.anticon-upload')).not.toBeNull();
  expect(newButton.querySelector('.anticon-plus')).not.toBeNull();
  expect(importButton.compareDocumentPosition(newButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(disabledOpacity(importButton)).toBe(false);

  cleanup();
  granted.values = [];
  render(<SkillPage />);
  expect(disabledOpacity(screen.getByRole('button', { name: /common\.import/ }))).toBe(true);
}, 20000);

it('opens the new agent settings after a successful import and stays on the list after a failure', async () => {
  importAgent.mockResolvedValueOnce({ id: 42, name: '助手 2', notes: ['名称已调整为「助手 2」'] });
  const { unmount } = render(<SkillPage />);
  const file = new File(['zip'], 'agent.zip', { type: 'application/zip' });
  fireEvent.change(screen.getByLabelText('common.import'), { target: { files: [file] } });
  await waitFor(() => expect(push).toHaveBeenCalledWith('/opspilot/skill/detail/settings?id=42&name=%E5%8A%A9%E6%89%8B%202'));
  expect(sessionStorage.getItem('opspilot-agent-import-notes')).toContain('助手 2');
  unmount();
  sessionStorage.removeItem('opspilot-agent-import-notes');

  importAgent.mockRejectedValueOnce(new Error('当前版本缺少相关工具：kube。请升级版本。'));
  render(<SkillPage />);
  fireEvent.change(screen.getByLabelText('common.import'), { target: { files: [file] } });
  await waitFor(() => expect(importAgent).toHaveBeenCalledTimes(2));
  expect(push).toHaveBeenCalledTimes(1);
});
