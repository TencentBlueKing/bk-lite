import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { ShareModeProvider } from '@/app/ops-analysis/context/shareMode';
import ReportWidgetCard from '@/app/ops-analysis/components/reportWidgetCard';
import { WidgetCsvExportRegistryProvider } from '@/app/ops-analysis/context/widgetCsvExportRegistry';

vi.mock('@dnd-kit/sortable', () => ({
  useSortable: () => ({
    attributes: {},
    listeners: {},
    setNodeRef: vi.fn(),
    transform: null,
    transition: undefined,
  }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

let failWidgetRender = false;

vi.mock('@/app/ops-analysis/components/widgetDataRenderer', () => ({
  default: function WidgetRuntimeMock(props: {
    widgetId: string;
    onRenderStatus?: (result: { widgetId: string; status: string }) => void;
  }) {
    React.useEffect(() => {
      if (!failWidgetRender) return;
      props.onRenderStatus?.({ widgetId: props.widgetId, status: 'failed' });
    }, [props]);
    return <div data-testid="widget-runtime" />;
  },
}));

const section = {
  id: 'section-1',
  valueConfig: {
    name: 'CMDB 模型实例明细',
    chartType: 'table',
  },
};

const sceneSection = {
  id: 'section-topo',
  valueConfig: {
    name: '网络状态拓扑',
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
  failWidgetRender = false;
  cleanup();
});

describe('ReportWidgetCard copy menu', () => {
  it('includes 复制 for a data widget in edit mode', async () => {
    const user = userEvent.setup();
    render(
      <ReportWidgetCard
        section={section as never}
        index={0}
        unifiedFilterValues={{}}
        filterDefinitions={[]}
        filterSearchVersion={0}
        editing
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onCopy={vi.fn()}
      />,
    );

    await user.hover(screen.getByRole('button', { name: 'common.more' }));
    expect(await screen.findByText('common.copy')).toBeTruthy();
  });

  it('omits 复制 in view mode', () => {
    render(
      <ReportWidgetCard
        section={section as never}
        index={0}
        unifiedFilterValues={{}}
        filterDefinitions={[]}
        filterSearchVersion={0}
        editing={false}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onCopy={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: 'common.more' })).toBeNull();
    expect(screen.queryByText('common.copy')).toBeNull();
  });

  it('omits 复制 entirely for a networkStatusTopology scene widget', async () => {
    const user = userEvent.setup();
    render(
      <ReportWidgetCard
        section={sceneSection as never}
        index={0}
        unifiedFilterValues={{}}
        filterDefinitions={[]}
        filterSearchVersion={0}
        editing
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onCopy={vi.fn()}
      />,
    );

    await user.hover(screen.getByRole('button', { name: 'common.more' }));
    expect(await screen.findByText('common.edit')).toBeTruthy();
    expect(screen.queryByText('common.copy')).toBeNull();
    expect(screen.getByText('common.delete')).toBeTruthy();
  });

  it('omits 复制 in share mode', async () => {
    const user = userEvent.setup();
    render(
      <ReportWidgetCard
        section={section as never}
        index={0}
        unifiedFilterValues={{}}
        filterDefinitions={[]}
        filterSearchVersion={0}
        editing
        shareMode
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onCopy={vi.fn()}
      />,
    );

    await user.hover(screen.getByRole('button', { name: 'common.more' }));
    expect(await screen.findByText('common.edit')).toBeTruthy();
    expect(screen.queryByText('common.copy')).toBeNull();
    expect(screen.getByText('common.delete')).toBeTruthy();
  });

  it('omits 复制 on a builtin report', async () => {
    const user = userEvent.setup();
    render(
      <ReportWidgetCard
        section={section as never}
        index={0}
        unifiedFilterValues={{}}
        filterDefinitions={[]}
        filterSearchVersion={0}
        editing
        isBuiltIn
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onCopy={vi.fn()}
      />,
    );

    await user.hover(screen.getByRole('button', { name: 'common.more' }));
    expect(await screen.findByText('common.edit')).toBeTruthy();
    expect(screen.queryByText('common.copy')).toBeNull();
    expect(screen.getByText('common.delete')).toBeTruthy();
  });
});

const renderCard = (
  props: Partial<React.ComponentProps<typeof ReportWidgetCard>> = {},
) => render(
  <ReportWidgetCard
    section={section as never}
    index={0}
    unifiedFilterValues={{}}
    filterDefinitions={[]}
    filterSearchVersion={0}
    editing={false}
    onEdit={vi.fn()}
    onDelete={vi.fn()}
    onCopy={vi.fn()}
    {...props}
  />,
);

describe('ReportWidgetCard csv export', () => {
  it('shows a hover-only export icon after the runtime slot in view mode', async () => {
    renderCard();
    const button = screen.getByRole('button', { name: 'dashboard.exportCsv' });
    expect(button.getAttribute('data-csv-export-hover')).toBe('true');
    expect(button.getAttribute('data-export-hidden')).toBe('true');
    expect(button.className).toContain('opacity-0');
    expect(button.className).toContain('shrink-0');
    expect(button.className).toContain('cursor-pointer');
    expect(button.className).not.toContain('absolute');
    fireEvent.mouseEnter(button);
    const tooltip = await screen.findByRole('tooltip');
    expect(tooltip.textContent).toBe('dashboard.exportCsv');
    expect(button.closest('.group')?.contains(tooltip)).toBe(false);
    const slot = button.parentElement?.querySelector('.overflow-x-auto');
    expect(slot).toBeTruthy();
    expect(slot!.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'common.more' })).toBeNull();
    expect(screen.queryByRole('menuitem')).toBeNull();
  });

  it('keeps retry to the left of the export icon when the widget failed', async () => {
    failWidgetRender = true;
    renderCard();
    const retry = await screen.findByRole('button', { name: 'common.retry' });
    const exportButton = screen.getByRole('button', { name: 'dashboard.exportCsv' });
    expect(
      retry.compareDocumentPosition(exportButton) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('puts export between copy and delete in the edit menu and hides the menu from export', async () => {
    const user = userEvent.setup();
    const { container } = renderCard({ editing: true });
    await user.hover(screen.getByRole('button', { name: 'common.more' }));
    const items = await screen.findAllByRole('menuitem');
    expect(items.map((item) => item.textContent)).toEqual([
      'common.edit',
      'common.copy',
      'dashboard.exportCsv',
      'common.delete',
    ]);
    expect(container.querySelector('[data-export-hidden="true"]')).toBeTruthy();
    expect(container.querySelector('[data-export-expand="true"]')).toBeNull();
  });

  it('omits export for an unsupported chart and in share, fullscreen, screenshot, and pdf preparation', async () => {
    const user = userEvent.setup();
    renderCard({ section: sceneSection as never, editing: true });
    await user.hover(screen.getByRole('button', { name: 'common.more' }));
    expect(await screen.findByText('common.edit')).toBeTruthy();
    expect(screen.queryByText('dashboard.exportCsv')).toBeNull();

    cleanup();
    renderCard({ shareMode: true });
    expect(screen.queryByRole('button', { name: 'dashboard.exportCsv' })).toBeNull();

    cleanup();
    renderCard({ editing: true, shareMode: true });
    await user.hover(screen.getByRole('button', { name: 'common.more' }));
    expect(await screen.findByText('common.delete')).toBeTruthy();
    expect(screen.queryByText('dashboard.exportCsv')).toBeNull();

    cleanup();
    renderCard({ isFullscreen: true });
    expect(screen.queryByRole('button', { name: 'dashboard.exportCsv' })).toBeNull();

    cleanup();
    renderCard({ renderMode: true });
    expect(screen.queryByRole('button', { name: 'dashboard.exportCsv' })).toBeNull();

    cleanup();
    renderCard({ editing: true, renderMode: true });
    await user.hover(screen.getByRole('button', { name: 'common.more' }));
    expect(screen.queryByText('dashboard.exportCsv')).toBeNull();

    cleanup();
    renderCard({ pdfExportPreparing: true });
    expect(screen.queryByRole('button', { name: 'dashboard.exportCsv' })).toBeNull();

    cleanup();
    renderCard({ editing: true, pdfExportPreparing: true });
    await user.hover(screen.getByRole('button', { name: 'common.more' }));
    expect(await screen.findByText('common.edit')).toBeTruthy();
    expect(screen.queryByText('dashboard.exportCsv')).toBeNull();
  });

  it('runs the registered exporter for the section', () => {
    const run = vi.fn().mockResolvedValue(true);
    render(
      <WidgetCsvExportRegistryProvider registry={{
        register: () => () => undefined,
        run,
        publishWidgetRawData: () => undefined,
        readWidgetRawData: () => undefined,
      }}>
        <ReportWidgetCard
          section={section as never}
          index={0}
          unifiedFilterValues={{}}
          filterDefinitions={[]}
          filterSearchVersion={0}
          editing={false}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      </WidgetCsvExportRegistryProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'dashboard.exportCsv' }));
    expect(run).toHaveBeenCalledWith('section-1', { title: 'CMDB 模型实例明细' });
  });
});

const linkedSection = {
  ...section,
  valueConfig: {
    ...section.valueConfig,
    interaction: {
      kind: 'title' as const,
      name: '查看详情',
      url: '/ops',
      openMode: 'sameTab' as const,
    },
  },
};

const isLastIn = (node: HTMLElement, root: HTMLElement) => {
  const last = root.lastElementChild;
  return last === node || Boolean(last?.contains(node));
};

describe('Report title link', () => {
  it('places the chevron after retry and the csv download', async () => {
    failWidgetRender = true;
    renderCard({ section: linkedSection as never });
    const link = await screen.findByRole('button', { name: '查看详情' });
    const retry = await screen.findByRole('button', { name: 'common.retry' });
    const csv = screen.getByRole('button', { name: 'dashboard.exportCsv' });
    const title = screen.getByRole('heading', { name: 'CMDB 模型实例明细' });
    const header = title.closest('.mb-2') as HTMLElement;

    expect(link.querySelector('.anticon-export')).toBeTruthy();
    expect(link.querySelector('.anticon-share-alt')).toBeNull();
    expect(link.className).toContain('w-0');
    expect(link.className).toContain('group-hover:w-5');
    expect(link.getAttribute('data-export-hidden')).toBe('true');
    expect(link.className).toContain('no-drag');
    expect(title.className).toContain('truncate');
    expect(title.closest('button')).toBeNull();
    expect(retry.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(csv.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(isLastIn(link, header)).toBe(true);
  });

  it('places the jump icon before the edit menu so the menu stays at the end', () => {
    renderCard({ section: linkedSection as never, editing: true });
    const link = screen.getByRole('button', { name: '查看详情' });
    const more = screen.getByRole('button', { name: 'common.more' });

    const header = screen.getByRole('heading', { name: 'CMDB 模型实例明细' }).closest('.mb-2') as HTMLElement;
    expect(link.compareDocumentPosition(more) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(link.className).toContain('-mr-2');
    expect(isLastIn(more, header)).toBe(true);
  });

  it('hides the chevron on the share surface', () => {
    render(
      <ShareModeProvider value>
        <ReportWidgetCard
          section={linkedSection as never}
          index={0}
          unifiedFilterValues={{}}
          filterDefinitions={[]}
          filterSearchVersion={0}
          editing={false}
          shareMode
          onEdit={vi.fn()}
          onDelete={vi.fn()}
          onCopy={vi.fn()}
        />
      </ShareModeProvider>,
    );
    expect(screen.getByText('CMDB 模型实例明细')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '查看详情' })).toBeNull();
  });
});
