import React from 'react';
import { cleanup, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import OrganizationAssignmentModal from '../organization-assignment-modal';
import { renderWithApmIntl } from '@/app/apm/__tests__/intl';

vi.mock('@/components/group-tree-select', () => ({
  default: () => <div>组织选择器</div>,
}));

afterEach(cleanup);

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
});

describe('OrganizationAssignmentModal', () => {
  it('关闭时不创建表单实例，避免控制台 useForm 警告', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    renderWithApmIntl(
      <OrganizationAssignmentModal
        open={false}
        organizationIds={[]}
        title="分配组织"
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.queryByText('组织选择器')).toBeNull();

    await new Promise((resolve) => setTimeout(resolve, 100));

    expect(error.mock.calls.some(([message]) => String(message).includes('useForm'))).toBe(false);
    error.mockRestore();
  });
});
