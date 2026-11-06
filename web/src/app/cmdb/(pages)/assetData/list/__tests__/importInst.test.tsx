import React, { createRef } from 'react';
import { act, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import ImportInst, { type FieldModalRef } from '../importInst';

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/context/auth', () => ({ useAuth: () => ({ token: 'token' }) }));
vi.mock('next-auth/react', () => ({ useSession: () => ({ data: null }) }));
vi.mock('@/app/cmdb/api/transfer', () => ({ useTransferApi: () => ({ importFile: vi.fn() }) }));
Object.defineProperty(window, 'matchMedia', { value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }), writable: true });

it('opens the import dialog when crypto.randomUUID is unavailable', async () => {
  const getRandomValues = vi.fn((values: Uint8Array) => {
    values.fill(0);
    return values;
  });
  vi.stubGlobal('crypto', { getRandomValues });
  try {
    const ref = createRef<FieldModalRef>();
    render(<ImportInst ref={ref} canSubmit onSubmitted={vi.fn()} />);
    await act(async () => {
      ref.current?.showModal({ subTitle: '主机', title: '导入', model_id: 'host' });
    });
    expect(screen.getByText('导入')).toBeTruthy();
    expect(getRandomValues).toHaveBeenCalled();
  } finally {
    vi.unstubAllGlobals();
  }
});
