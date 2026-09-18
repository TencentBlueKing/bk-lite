import React, { useState } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import OpenApiTokenCreateModal from '../OpenApiTokenCreateModal';
import type { OpenApiTokenCreateFormValues, OpenApiTokenServiceCatalog } from '../types';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

beforeAll(() => {
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

afterEach(() => {
  cleanup();
});

const catalog: OpenApiTokenServiceCatalog[] = [{
  name: 'alerts',
  kind: 'internal',
  label: 'alerts',
  endpoints: [
    { key: 'GET alerts/list', label: '列表', method: 'GET', path: 'alerts/list' },
    { key: 'POST alerts/close', label: '关闭', method: 'POST', path: 'alerts/close' },
  ],
}];

const initialValues: OpenApiTokenCreateFormValues = {
  name: '测试1',
  systemId: 'itsm',
  scopeMode: 'allowlist',
  scopeEndpoints: ['GET alerts/list'],
};

const checkedState = () => (
  (screen.getAllByRole('checkbox') as HTMLInputElement[]).map((box) => box.checked)
);

const SubmitHarness: React.FC<{ onSubmit: () => Promise<void> }> = ({ onSubmit }) => {
  const [submitting, setSubmitting] = useState(false);
  return (
    <OpenApiTokenCreateModal
      open
      editing
      kind="system"
      catalog={catalog}
      initialValues={initialValues}
      submitting={submitting}
      onCancel={vi.fn()}
      onSubmit={async () => {
        setSubmitting(true);
        await onSubmit();
      }}
    />
  );
};

describe('OpenApiTokenCreateModal', () => {
  it('keeps in-progress allowlist checks when parent re-renders the same record', () => {
    const { rerender } = render(
      <OpenApiTokenCreateModal
        open
        editing
        kind="system"
        catalog={catalog}
        initialValues={initialValues}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText('POST alerts/close'));
    expect(checkedState()).toEqual([true, true, true]);

    rerender(
      <OpenApiTokenCreateModal
        open
        editing
        submitting
        kind="system"
        catalog={catalog}
        initialValues={{ ...initialValues }}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(checkedState()).toEqual([true, true, true]);
  });

  it('keeps newly checked endpoints while the edit request is in flight', async () => {
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    const onSubmit = vi.fn(() => pending);

    render(<SubmitHarness onSubmit={onSubmit} />);
    fireEvent.click(screen.getByText('POST alerts/close'));
    expect(checkedState()).toEqual([true, true, true]);

    fireEvent.click(screen.getByRole('button', { name: 'common.confirm' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(checkedState()).toEqual([true, true, true]);
    release();
    await pending;
  });
});
