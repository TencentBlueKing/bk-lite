import React, { createRef } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import BatchEditOrganizations from '../batchEditOrganizations';
import type { ModalRef } from '@/app/node-manager/types';

const apiMocks = vi.hoisted(() => ({
  batchUpdateNodeOrganizations: vi.fn()
}));

vi.mock('@/app/node-manager/api', () => ({
  default: () => apiMocks
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => {
      const translations: Record<string, string> = {
        'common.confirm': '确认',
        'common.cancel': '取消'
      };
      return translations[key] || fallback || key;
    }
  })
}));

vi.mock('@/components/operate-modal', () => ({
  default: ({ title, open, children, footer }: React.PropsWithChildren<{
    title: React.ReactNode;
    open: boolean;
    footer: React.ReactNode;
  }>) => open ? <div><h2>{title}</h2>{children}{footer}</div> : null
}));

vi.mock('@/components/group-tree-select', () => ({
  default: ({ onChange }: { onChange?: (value: number[]) => void }) => (
    <button type="button" onClick={() => onChange?.([7, 8])}>
      选择组织
    </button>
  )
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn()
  }));
});

describe('BatchEditOrganizations', () => {
  it('为选中的节点统一提交组织并通知列表刷新', async () => {
    apiMocks.batchUpdateNodeOrganizations.mockResolvedValue({ updated_count: 2 });
    const onSuccess = vi.fn();
    const ref = createRef<ModalRef>();

    render(<BatchEditOrganizations ref={ref} onSuccess={onSuccess} />);
    act(() => {
      ref.current?.showModal({ type: 'batchEdit', ids: ['node-1', 'node-2'] });
    });

    fireEvent.click(await screen.findByRole('button', { name: '选择组织' }));
    fireEvent.click(screen.getByRole('button', { name: /确\s*认/ }));

    await waitFor(() => {
      expect(apiMocks.batchUpdateNodeOrganizations).toHaveBeenCalledWith({
        node_ids: ['node-1', 'node-2'],
        organizations: [7, 8]
      });
      expect(onSuccess).toHaveBeenCalledTimes(1);
    });
  });
});
