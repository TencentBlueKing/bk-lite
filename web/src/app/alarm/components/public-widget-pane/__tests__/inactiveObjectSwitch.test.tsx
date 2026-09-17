import React, { useEffect } from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { PublicWidgetPane } from '../index';

const fetches = vi.hoisted(() => ({ monitorIds: [] as string[] }));

function SpyMonitorWidget({ monitorId }: { monitorId: string }) {
  useEffect(() => {
    fetches.monitorIds.push(monitorId);
  }, [monitorId]);
  return <div data-testid="spy-monitor">{monitorId}</div>;
}

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
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => {
  cleanup();
  fetches.monitorIds = [];
});

describe('alarm public pane object switch', () => {
  it('does not refetch a hidden monitor pane when the current object changes', async () => {
    const loadWidget = vi.fn(async () => ({ default: SpyMonitorWidget }));
    const { rerender } = render(
      <PublicWidgetPane
        active
        loadWidget={loadWidget}
        identifier="app3d-demo-host-02"
        identifierProp="monitorId"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('spy-monitor').textContent).toBe(
        'app3d-demo-host-02',
      );
    });
    expect(fetches.monitorIds).toEqual(['app3d-demo-host-02']);

    rerender(
      <PublicWidgetPane
        active={false}
        loadWidget={loadWidget}
        identifier="app3d-demo-host-02"
        identifierProp="monitorId"
      />,
    );
    rerender(
      <PublicWidgetPane
        active={false}
        loadWidget={loadWidget}
        identifier="app3d-demo-host-09"
        identifierProp="monitorId"
      />,
    );

    await new Promise((resolve) => setTimeout(resolve, 80));
    expect(fetches.monitorIds).toEqual(['app3d-demo-host-02']);
    expect(screen.getByTestId('spy-monitor').textContent).toBe(
      'app3d-demo-host-02',
    );
  });

  it('loads the new identifier once the hidden pane is activated again', async () => {
    const loadWidget = vi.fn(async () => ({ default: SpyMonitorWidget }));
    const { rerender } = render(
      <PublicWidgetPane
        active
        loadWidget={loadWidget}
        identifier="app3d-demo-host-02"
        identifierProp="monitorId"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('spy-monitor').textContent).toBe(
        'app3d-demo-host-02',
      );
    });

    rerender(
      <PublicWidgetPane
        active={false}
        loadWidget={loadWidget}
        identifier="app3d-demo-host-09"
        identifierProp="monitorId"
      />,
    );
    rerender(
      <PublicWidgetPane
        active
        loadWidget={loadWidget}
        identifier="app3d-demo-host-09"
        identifierProp="monitorId"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('spy-monitor').textContent).toBe(
        'app3d-demo-host-09',
      );
    });
    expect(fetches.monitorIds).toEqual([
      'app3d-demo-host-02',
      'app3d-demo-host-09',
    ]);
  });

  it('keeps the object switcher on the host toolbar and does not add a refresh control', async () => {
    const loadWidget = vi.fn(async () => ({ default: SpyMonitorWidget }));
    render(
      <PublicWidgetPane
        active
        loadWidget={loadWidget}
        identifier="app3d-demo-host-02"
        identifierProp="monitorId"
        toolbarStart={<div data-testid="object-switcher">host-a</div>}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('spy-monitor')).toBeTruthy();
    });

    expect(screen.getByTestId('object-switcher')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'common.refresh' })).toBeNull();
  });

  it('renders headerAction on the same row opposite toolbarStart', async () => {
    function SpyActionWidget({
      onHeaderAction,
    }: {
      onHeaderAction?: (node: React.ReactNode) => void;
    }) {
      useEffect(() => {
        onHeaderAction?.(<button type="button">custom-action</button>);
        return () => onHeaderAction?.(null);
      }, [onHeaderAction]);
      return <div>spy-content</div>;
    }
    const loadWidget = vi.fn(async () => ({ default: SpyActionWidget }));
    render(
      <PublicWidgetPane
        active
        loadWidget={loadWidget}
        identifier="inst-01"
        identifierProp="instUuid"
        toolbarStart={<div data-testid="object-switcher">host-a</div>}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('custom-action')).toBeTruthy();
    });

    const switcher = screen.getByTestId('object-switcher');
    const action = screen.getByText('custom-action');
    expect(switcher.closest('.justify-between')).toBe(action.closest('.justify-between'));
  });

  it('replaces host chrome with embed toolbar so the switcher sits beside back, not centered', async () => {
    function SpyEmbedWidget({
      onHeaderAction,
      onEmbedToolbar,
      objectSwitcher,
    }: {
      onHeaderAction?: (node: React.ReactNode) => void;
      onEmbedToolbar?: (node: React.ReactNode) => void;
      objectSwitcher?: React.ReactNode;
    }) {
      useEffect(() => {
        onHeaderAction?.(null);
        onEmbedToolbar?.(
          <div data-testid="embed-toolbar" className="flex w-full min-w-0 items-center gap-3">
            <button type="button">back-to-timeline</button>
            {objectSwitcher}
            <div className="min-w-0 flex-1" />
            <a href="/cmdb">open-in-cmdb</a>
          </div>,
        );
        return () => onEmbedToolbar?.(null);
      }, [objectSwitcher, onEmbedToolbar, onHeaderAction]);
      return <div>detail-body</div>;
    }
    const loadWidget = vi.fn(async () => ({ default: SpyEmbedWidget }));
    render(
      <PublicWidgetPane
        active
        loadWidget={loadWidget}
        identifier="inst-01"
        identifierProp="instUuid"
        toolbarStart={<div data-testid="object-switcher">host-a</div>}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('embed-toolbar')).toBeTruthy();
    });

    expect(screen.getByText('back-to-timeline')).toBeTruthy();
    expect(screen.getByTestId('object-switcher')).toBeTruthy();
    expect(screen.getByText('open-in-cmdb')).toBeTruthy();
    expect(document.querySelector('.justify-between')).toBeNull();
    expect(screen.queryByText('custom-action')).toBeNull();
  });
});
