import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

const INST_UUID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

const apis = vi.hoisted(() => ({
  getInstanceDetail: vi.fn(async () => ({
    inst_uuid: INST_UUID,
    model_id: 'host',
    inst_name: 'web-1',
  })),
  getModelAttrGroupsFullInfo: vi.fn(async () => ({
    groups: [{ id: 1, name: 'base', attrs: [] }],
  })),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/app/cmdb/api', () => ({
  useInstanceApi: () => ({
    getInstanceDetail: async (...args: unknown[]) =>
      apis.getInstanceDetail(...args),
  }),
  useModelApi: () => ({
    getModelAttrGroupsFullInfo: async (...args: unknown[]) =>
      apis.getModelAttrGroupsFullInfo(...args),
  }),
}));

vi.mock('@/app/cmdb/context/common', () => ({
  useCmdbUserList: () => [],
}));

vi.mock('@/app/cmdb/(pages)/assetData/detail/baseInfo/list', () => ({
  default: () => <div data-testid="base-info-list" />,
}));

import BaseInfoWidget from '../BaseInfoWidget';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('cmdb base info public widget fetch once', () => {
  it('does not retrigger detail bootstrap when API identities change each render', async () => {
    render(<BaseInfoWidget instUuid={INST_UUID} />);
    await waitFor(() => {
      expect(screen.getByTestId('base-info-list')).toBeTruthy();
    });
    expect(apis.getInstanceDetail).toHaveBeenCalledTimes(1);
    expect(apis.getModelAttrGroupsFullInfo).toHaveBeenCalledTimes(1);
    const settled = apis.getInstanceDetail.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 80));
    expect(apis.getInstanceDetail.mock.calls.length).toBe(settled);
  });

  it('delegates open-in-cmdb action to onHeaderAction when provided', async () => {
    const onHeaderAction = vi.fn();
    const { unmount } = render(
      <BaseInfoWidget instUuid={INST_UUID} onHeaderAction={onHeaderAction} />,
    );
    await waitFor(() => {
      expect(onHeaderAction).toHaveBeenCalled();
      const lastCallArg = onHeaderAction.mock.calls.at(-1)?.[0];
      expect(lastCallArg).toBeTruthy();
    });
    expect(screen.queryByRole('link', { name: 'Model.openInCmdb' })).toBeNull();
    unmount();
    expect(onHeaderAction).toHaveBeenLastCalledWith(null);
  });

  it('renders open-in-cmdb link in self when onHeaderAction is absent', async () => {
    render(<BaseInfoWidget instUuid={INST_UUID} />);
    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Model.openInCmdb' })).toBeTruthy();
    });
  });
});
