import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, waitFor } from 'storybook/test';
import React from 'react';
import ComTable from './comTable';
import EventTable from './eventTable/eventTable';

const rows = Array.from({ length: 16 }, (_, index) => ({
  inst_uuid: `4c4b7918-0798-4c0e-9b2a-${String(index).padStart(4, '0')}`,
  inst_name: index < 5 ? `bare-0${index + 1}` : `本地演示-host-0${index}`,
  model_id: 'host',
  ip_addr: `10.24.10.${index + 1}`,
  cloud: 'app3d-demo-host',
}));

const wideColumns = [
  { key: 'inst_uuid', title: '实例UUID', visible: true, order: 0, width: 220 },
  { key: 'inst_name', title: '实例名', visible: true, order: 1, width: 180 },
  { key: 'model_id', title: '模型', visible: true, order: 2, width: 120 },
  { key: 'ip_addr', title: 'ip_addr', visible: true, order: 3, width: 160 },
  { key: 'cloud', title: 'cloud', visible: true, order: 4, width: 180 },
];

const narrowColumns = wideColumns.map((column) => ({ ...column, width: 90 }));

const dataSource = {
  params: [{ name: 'page' }, { name: 'page_size' }],
  field_schema: wideColumns.map((column) => ({
    key: column.key,
    title: column.title,
    value_type: 'string',
  })),
} as any;

// 画布卡片和配置预览列的类名夹具，不是登录后的 Ant Design Drawer。
const SavedCard = ({
  width,
  height,
  columns,
  count,
  label,
  scale = 1,
}: {
  width: number;
  height: number;
  columns: typeof wideColumns;
  count: number;
  label: string;
  scale?: number;
}) => (
  <div
    data-card={label}
    className="widget group relative flex h-full flex-col overflow-hidden rounded-lg p-3"
    style={{
      width,
      height,
      background: 'var(--color-bg-1, #fff)',
      border: '1px solid var(--color-border-1, #e5e6eb)',
    }}
  >
    <div className="widget-header flex min-w-0 items-start gap-2">
      <div className="min-w-0 flex-1">
        <h4 className="truncate text-[14px] font-medium leading-5 text-(--color-text-2)">
          CMDB 实例查询
        </h4>
      </div>
    </div>
    <div className="widget-body h-full min-h-0 flex-1" style={{ overflow: 'hidden' }}>
      <div style={{ position: 'relative', height: '100%' }}>
        <ComTable
          rawData={{
            items: count === 0 ? [] : rows.slice(0, Math.min(count, rows.length)),
            count,
          }}
          loading={false}
          dataSource={dataSource}
          screenRenderContext={scale === 1 ? undefined : {
            enabled: true,
            fitScale: 1,
            screenDensity: scale,
            screenUiScale: scale,
            widgetDensity: scale,
            widgetUiScale: scale,
            layoutMode: 'viewportPixels',
          }}
          config={{
            chartType: 'table',
            chartThemeMode: scale === 1 ? 'default' : 'screen-dark',
            tableConfig: { columns },
          }}
        />
      </div>
    </div>
  </div>
);

const eventRows = Array.from({ length: 8 }, (_, index) => ({
  id: `evt-${index + 1}`,
  summary: `告警-${index + 1}`,
}));

const EventSavedCard = ({
  width,
  height,
  label,
  scale = 1,
}: {
  width: number;
  height: number;
  label: string;
  scale?: number;
}) => (
  <div
    data-card={label}
    className="widget group relative flex h-full flex-col overflow-hidden rounded-lg p-3"
    style={{
      width,
      height,
      background: 'var(--color-bg-1, #fff)',
      border: '1px solid var(--color-border-1, #e5e6eb)',
    }}
  >
    <div className="widget-header flex min-w-0 items-start gap-2">
      <div className="min-w-0 flex-1">
        <h4 className="truncate text-[14px] font-medium leading-5 text-(--color-text-2)">
          事件表
        </h4>
      </div>
    </div>
    <div className="widget-body h-full min-h-0 flex-1" style={{ overflow: 'hidden' }}>
      <div style={{ position: 'relative', height: '100%' }}>
        <EventTable
          rawData={{ items: eventRows, count: 16 }}
          loading={false}
          dataSource={dataSource}
          screenRenderContext={scale === 1 ? undefined : {
            enabled: true,
            fitScale: 1,
            screenDensity: scale,
            screenUiScale: scale,
            widgetDensity: scale,
            widgetUiScale: scale,
            layoutMode: 'viewportPixels',
          }}
          config={{
            chartType: 'eventTable',
            chartThemeMode: scale === 1 ? 'default' : 'screen-dark',
            tableConfig: {
              columns: [{ key: 'summary', title: '摘要', visible: true, order: 0, width: 420 }],
            },
          }}
        />
      </div>
    </div>
  </div>
);

const PreviewCard = ({
  columns,
  count,
  label,
}: {
  columns: typeof wideColumns;
  count: number;
  label: string;
}) => (
  <div
    data-card={label}
    className="flex h-[640px] w-[480px] min-h-0 flex-col overflow-hidden rounded-lg border border-(--color-border-1) bg-(--color-bg)"
  >
    <div className="shrink-0 px-3 pt-3">
      <div className="text-sm font-medium">CMDB 实例查询</div>
      <p className="mt-1 line-clamp-2 text-xs text-(--color-text-3)">按模型查询实例</p>
    </div>
    <div className="flex min-h-0 flex-1 flex-col px-3 pb-3">
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg bg-(--color-fill-1)/40">
        <div className="h-full min-h-0 w-full flex-1 overflow-hidden">
          <div className="flex h-full min-h-0 w-full flex-col">
            <div className="mb-1 max-w-full shrink-0 overflow-x-auto" />
            <div className="h-full min-h-0 flex-1">
              <div style={{ position: 'relative', height: '100%' }}>
                <ComTable
                  rawData={{
                    items: count === 0 ? [] : rows,
                    count,
                  }}
                  loading={false}
                  dataSource={dataSource}
                  config={{
                    chartType: 'table',
                    tableConfig: { columns },
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
);

const clipParentOf = (element: HTMLElement, card: HTMLElement) => {
  let node = element.parentElement;
  while (node && node !== card) {
    const overflow = getComputedStyle(node).overflow;
    if (overflow === 'hidden' || overflow === 'auto' || overflow === 'scroll') return node;
    node = node.parentElement;
  }
  return card;
};

const measure = (card: HTMLElement) => {
  const cardBox = card.getBoundingClientRect();
  const pagination = card.querySelector<HTMLElement>('.ant-pagination');
  const pageItem = card.querySelector<HTMLElement>('.ant-pagination-item, .ant-pagination-item-active');
  const sizeChanger = card.querySelector<HTMLElement>('.ant-pagination-options .ant-select');
  const body = card.querySelector<HTMLElement>('.ant-table-body');
  const clipParent = pagination ? clipParentOf(pagination, card) : card;
  const clipBottom = clipParent.getBoundingClientRect().bottom;
  const overflowPast = (element: HTMLElement | null) =>
    element ? Math.round((element.getBoundingClientRect().bottom - clipBottom) * 10) / 10 : null;
  return {
    label: card.dataset.card,
    cardHeight: Math.round(cardBox.height),
    paginationClip: overflowPast(pagination),
    pageItemClip: overflowPast(pageItem),
    sizeChangerClip: overflowPast(sizeChanger),
    horizontalOverflow: body ? body.scrollWidth - body.clientWidth : null,
    verticalOverflow: body ? body.scrollHeight - body.clientHeight : null,
  };
};

const Gallery = () => {
  const [report, setReport] = React.useState('pending');

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      const cards = Array.from(document.querySelectorAll<HTMLElement>('[data-card]'));
      setReport(JSON.stringify(cards.map(measure), null, 2));
    }, 600);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="flex flex-col gap-6 bg-(--color-fill-1) p-4">
      <SavedCard
        label="saved-wide"
        width={770}
        height={519}
        columns={wideColumns}
        count={16}
      />
      <SavedCard
        label="saved-short"
        width={770}
        height={360}
        columns={wideColumns}
        count={16}
      />
      <SavedCard
        label="saved-narrow"
        width={770}
        height={519}
        columns={narrowColumns}
        count={16}
      />
      <SavedCard
        label="saved-280"
        width={770}
        height={280}
        columns={wideColumns}
        count={16}
      />
      <SavedCard
        label="scale-half"
        width={770}
        height={519}
        columns={wideColumns}
        count={16}
        scale={0.5}
      />
      <SavedCard
        label="scale-double"
        width={770}
        height={519}
        columns={wideColumns}
        count={16}
        scale={2}
      />
      <SavedCard
        label="scale-double-280"
        width={770}
        height={280}
        columns={wideColumns}
        count={16}
        scale={2}
      />
      <EventSavedCard label="event-280" width={770} height={280} />
      <EventSavedCard label="event-scale-half" width={770} height={519} scale={0.5} />
      <EventSavedCard label="event-scale-double" width={770} height={519} scale={2} />
      <SavedCard
        label="saved-empty"
        width={770}
        height={519}
        columns={wideColumns}
        count={0}
      />
      <PreviewCard label="preview-wide" columns={wideColumns} count={16} />
      <PreviewCard label="preview-empty" columns={narrowColumns} count={0} />
      <pre data-measure>{report}</pre>
    </div>
  );
};

const meta: Meta = {
  title: 'ops-analysis/tableCardPagination',
  component: Gallery,
};

export default meta;

type Story = StoryObj;

export const GalleryStory: Story = {
  name: 'gallery',
  render: () => <Gallery />,
  play: async () => {
    await waitFor(() => {
      const text = document.querySelector('[data-measure]')?.textContent || '';
      expect(text).not.toBe('pending');
      const rows = JSON.parse(text) as Array<{
        label: string;
        paginationClip: number | null;
        pageItemClip: number | null;
        sizeChangerClip: number | null;
        horizontalOverflow: number | null;
      }>;
      for (const row of rows) {
        expect(row.paginationClip ?? 0).toBeLessThanOrEqual(0);
        expect(row.pageItemClip ?? 0).toBeLessThanOrEqual(0);
        expect(row.sizeChangerClip ?? 0).toBeLessThanOrEqual(0);
      }
      const wide = rows.find((row) => row.label === 'saved-wide');
      const narrow = rows.find((row) => row.label === 'saved-narrow');
      const short = rows.find((row) => row.label === 'saved-short');
      const empty = rows.find((row) => row.label === 'saved-empty');
      expect(wide?.horizontalOverflow ?? 0).toBeGreaterThan(80);
      expect(narrow?.horizontalOverflow ?? 99).toBeLessThan(20);
      expect(short?.paginationClip).not.toBeNull();
      expect(empty?.paginationClip).toBeNull();
      for (const label of ['saved-280', 'scale-half', 'scale-double', 'scale-double-280', 'event-280', 'event-scale-half', 'event-scale-double']) {
        const row = rows.find((item) => item.label === label);
        expect(row?.paginationClip).toBe(0);
        expect(row?.pageItemClip).toBe(0);
        expect(row?.sizeChangerClip).toBe(0);
      }
    });
  },
};
