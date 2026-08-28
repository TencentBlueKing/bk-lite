import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import ScreenWidgetFrame from '../screenWidgetFrame';
import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const dataWidget: ScreenWidgetItem = {
  id: 'w-line',
  type: 'widget',
  chartType: 'line',
  title: 'CPU',
  x: 0,
  y: 0,
  w: 200,
  h: 120,
  zIndex: 1,
  valueConfig: { chartType: 'line' },
};

const sceneWidget: ScreenWidgetItem = {
  ...dataWidget,
  id: 'w-topo',
  chartType: 'networkStatusTopology',
  valueConfig: {
    chartType: 'networkStatusTopology',
    sceneWidgetType: 'networkStatusTopology',
  },
};

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(() => {
  cleanup();
});

const openMoreMenu = async () => {
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'common.more' }));
};

describe('ScreenWidgetFrame copy menu', () => {
  it('includes 复制 for a data widget in edit mode', async () => {
    render(
      <ScreenWidgetFrame item={dataWidget} editMode onConfigure={vi.fn()} onDelete={vi.fn()} onCopy={vi.fn()}>
        <div />
      </ScreenWidgetFrame>,
    );

    await openMoreMenu();
    expect(await screen.findByText('common.copy')).toBeTruthy();
  });

  it('omits 复制 entirely for a networkStatusTopology scene widget', async () => {
    render(
      <ScreenWidgetFrame item={sceneWidget} editMode onConfigure={vi.fn()} onDelete={vi.fn()} onCopy={vi.fn()}>
        <div />
      </ScreenWidgetFrame>,
    );

    await openMoreMenu();
    expect(await screen.findByText('opsAnalysis.screen.editWidget')).toBeTruthy();
    expect(screen.queryByText('common.copy')).toBeNull();
  });

  it('omits 复制 in view mode', () => {
    render(
      <ScreenWidgetFrame item={dataWidget} editMode={false} onConfigure={vi.fn()} onDelete={vi.fn()} onCopy={vi.fn()}>
        <div />
      </ScreenWidgetFrame>,
    );

    expect(screen.queryByRole('button', { name: 'common.more' })).toBeNull();
    expect(screen.queryByText('common.copy')).toBeNull();
  });

  it('omits 复制 in share mode', async () => {
    render(
      <ScreenWidgetFrame
        item={dataWidget}
        editMode
        shareMode
        onConfigure={vi.fn()}
        onDelete={vi.fn()}
        onCopy={vi.fn()}
      >
        <div />
      </ScreenWidgetFrame>,
    );

    await openMoreMenu();
    expect(await screen.findByText('opsAnalysis.screen.editWidget')).toBeTruthy();
    expect(screen.queryByText('common.copy')).toBeNull();
    expect(screen.getByText('opsAnalysis.screen.deleteWidget')).toBeTruthy();
  });

  it('omits 复制 on a builtin canvas', async () => {
    render(
      <ScreenWidgetFrame
        item={dataWidget}
        editMode
        isBuiltIn
        onConfigure={vi.fn()}
        onDelete={vi.fn()}
        onCopy={vi.fn()}
      >
        <div />
      </ScreenWidgetFrame>,
    );

    await openMoreMenu();
    expect(await screen.findByText('opsAnalysis.screen.editWidget')).toBeTruthy();
    expect(screen.queryByText('common.copy')).toBeNull();
    expect(screen.getByText('opsAnalysis.screen.deleteWidget')).toBeTruthy();
  });
});
