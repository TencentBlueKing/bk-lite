import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import ChannelModal from '../channelModal';

const state = vi.hoisted(() => ({
  channelType: 'tplpack',
  packs: [] as Array<Record<string, unknown>>,
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => ({
    get: (key: string) => (key === 'id' ? state.channelType : null),
  }),
}));

vi.mock('@/app/system-manager/api/channel', () => ({
  useChannelApi: () => ({
    addChannel: vi.fn(),
    updateChannel: vi.fn(),
    getChannelDetail: vi.fn(),
    testChannel: vi.fn(),
    getNotificationTagCatalog: () => Promise.resolve([]),
    getGroupAccountAssociationOptions: vi.fn(),
    getNotificationChannelPacks: () => Promise.resolve(state.packs),
  }),
}));

vi.mock('@/app/system-manager/hooks/useNatsChannelExtension', () => ({
  useNatsChannelExtension: () => ({
    mergeConfig: (config: Record<string, unknown>) => config,
    buildInitialConfig: () => ({}),
    getFieldDefinition: () => ({}),
    usesEnterpriseTestEndpoint: () => false,
    testChannel: vi.fn(),
  }),
}));

vi.mock('@/components/group-tree-select', () => ({
  default: () => <div data-testid="team" />,
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
  state.packs = [];
});

const field = {
  key: 'endpoint',
  label: 'Endpoint',
  field_type: 'input',
  required: true,
  secret: false,
};

function openModal() {
  render(
    <ChannelModal
      visible
      type="add"
      channelId={null}
      onClose={vi.fn()}
      onSuccess={vi.fn()}
    />,
  );
}

describe('ChannelModal pack parameters', () => {
  it('shows slots and test values for an ordered template pack, without a source select', async () => {
    state.channelType = 'tplpack';
    state.packs = [{
      key: 'tplpack',
      name: 'Tpl',
      description: '',
      delivery: 'template',
      parameter_mode: 'ordered',
      instance_template: [field],
    }];
    openModal();
    const add = await screen.findByRole('button', { name: 'system.channel.settings.cloudAddParameter' });
    fireEvent.click(add);
    expect(screen.getByText('system.channel.settings.cloudParameterSlot')).toBeTruthy();
    expect(screen.getByPlaceholderText('system.channel.settings.cloudTestValue')).toBeTruthy();
    expect(screen.queryByText('system.channel.settings.cloudSourceTitle')).toBeNull();
    expect(screen.queryByText('system.channel.settings.cloudSourceContent')).toBeNull();
    expect(screen.queryByText('system.channel.settings.cloudSourceLiteral')).toBeNull();
    expect(screen.queryByPlaceholderText('system.channel.settings.cloudParameterName')).toBeNull();
  });

  it('shows parameter names for a named template pack', async () => {
    state.channelType = 'namedpack';
    state.packs = [{
      key: 'namedpack',
      name: 'Named',
      description: '',
      delivery: 'template',
      parameter_mode: 'named',
      instance_template: [field],
    }];
    openModal();
    const add = await screen.findByRole('button', { name: 'system.channel.settings.cloudAddParameter' });
    fireEvent.click(add);
    expect(screen.getByPlaceholderText('system.channel.settings.cloudParameterName')).toBeTruthy();
    expect(screen.queryByText('system.channel.settings.cloudSourceTitle')).toBeNull();
    expect(screen.queryByText('system.channel.settings.cloudSourceContent')).toBeNull();
    expect(screen.queryByText('system.channel.settings.cloudSourceLiteral')).toBeNull();
  });

  it('hides the parameter table for a body pack', async () => {
    state.channelType = 'bodypack';
    state.packs = [{
      key: 'bodypack',
      name: 'Body',
      description: '',
      delivery: 'body',
      parameter_mode: null,
      instance_template: [field],
    }];
    openModal();
    await waitFor(() => {
      expect(screen.getByText('Endpoint')).toBeTruthy();
    });
    expect(screen.queryByRole('button', { name: 'system.channel.settings.cloudAddParameter' })).toBeNull();
    expect(screen.queryByText('system.channel.settings.parameters')).toBeNull();
  });
});
