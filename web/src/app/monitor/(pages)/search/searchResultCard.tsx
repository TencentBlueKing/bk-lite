'use client';

import React, { useCallback, useMemo, useState } from 'react';
import { CopyOutlined, DownloadOutlined } from '@ant-design/icons';
import { Button, Card, Dropdown, Segmented, Table, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { Dayjs } from 'dayjs';
import LineChart from '@/app/monitor/components/charts/lineChart';
import SeriesActivationHeader from '@/app/monitor/components/charts/seriesActivationHeader';
import { CHART_COLORS } from '@/app/monitor/constants';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import type { ChartItem } from '@/app/monitor/types/search';
import {
  getEnumValue,
  isStringArray,
  useFormatTime
} from '@/app/monitor/utils/common';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import {
  buildSearchChartTable,
  placeFrozenSampleSeries,
  resolveSearchTableKind,
  SEARCH_COLUMN_MIN_WIDTH,
  isSearchSeriesActive,
  toggleEmphasizedSeries,
  toCsv,
  toneForExtreme,
  type SearchChartPresentation,
  type SearchChartView,
  type SearchSeriesRow,
  type SearchTableKind,
  type SearchValueTone
} from './searchChartPresentation';

interface SearchHeaderCellProps extends React.ThHTMLAttributes<HTMLTableCellElement> {
  width?: number;
  resizeHandler?: (nextWidth: number) => void;
  'data-column-key'?: string;
}

const SearchTableHeaderCell: React.FC<SearchHeaderCellProps> = ({
  width,
  resizeHandler,
  children,
  className,
  ...rest
}) => {
  const onMouseDown = (event: React.MouseEvent) => {
    if (!resizeHandler || !width) return;
    event.preventDefault();
    event.stopPropagation();
    const startX = event.clientX;
    const startWidth = width;
    const onMove = (moveEvent: MouseEvent) => {
      resizeHandler(Math.max(startWidth + moveEvent.clientX - startX, SEARCH_COLUMN_MIN_WIDTH));
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  return (
    <th {...rest} className={['relative', className].filter(Boolean).join(' ')}>
      {children}
      {width && resizeHandler ? (
        <span
          role="separator"
          aria-orientation="vertical"
          className="absolute bottom-0 right-0 z-[2] h-full w-2 cursor-col-resize before:absolute before:right-1 before:top-1/2 before:h-4 before:w-px before:-translate-y-1/2 before:bg-[var(--color-border)] hover:before:bg-[var(--color-primary)]"
          onMouseDown={onMouseDown}
          onClick={(event) => event.stopPropagation()}
          onContextMenu={(event) => event.preventDefault()}
        />
      ) : null}
    </th>
  );
};

const stainedValue = (text: string, tone: SearchValueTone) => {
  if (!tone) return text;
  const className =
    tone === 'high'
      ? 'rounded-sm bg-[color-mix(in_srgb,var(--color-warning)_18%,transparent)] px-1 text-[var(--color-warning)]'
      : 'rounded-sm bg-[color-mix(in_srgb,var(--color-primary)_14%,transparent)] px-1 text-[var(--color-primary)]';
  return (
    <span data-tone={tone} className={className}>
      {text}
    </span>
  );
};

interface SearchResultCardProps {
  item: ChartItem;
  layoutMode: 'single' | 'double';
  presentation: SearchChartPresentation;
  showApplyAll: boolean;
  onPresentationChange: (next: SearchChartPresentation) => void;
  onApplyAll: () => void;
  onXRangeChange: (range: [Dayjs, Dayjs]) => void;
}

const Sparkline: React.FC<{ values: Array<number | null>; color: string }> = ({
  values,
  color
}) => {
  const finite = values.filter((value): value is number => value !== null);
  if (finite.length < 2) return <span className="text-[var(--color-text-3)]">--</span>;
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const span = max - min || 1;
  const width = 72;
  const height = 22;
  let path = '';
  let drawing = false;
  values.forEach((value, index) => {
    if (value === null) {
      drawing = false;
      return;
    }
    const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * (width - 2) + 1;
    const y = height - 2 - ((value - min) / span) * (height - 4);
    path += `${drawing ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
    drawing = true;
  });
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
      <path d={path} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
};

const SearchResultCard: React.FC<SearchResultCardProps> = ({
  item,
  layoutMode,
  presentation,
  showApplyAll,
  onPresentationChange,
  onApplyAll,
  onXRangeChange
}) => {
  const { t } = useTranslation();
  const { formatTime } = useFormatTime();
  const { findUnitNameById } = useUnitTransform();
  const model = useMemo(() => buildSearchChartTable(item.data), [item.data]);
  const seriesColor = useMemo(
    () =>
      Object.fromEntries(
        model.series.map((series, index) => [
          series.key,
          CHART_COLORS[index % CHART_COLORS.length]
        ])
      ),
    [model.series]
  );
  const tableKind = resolveSearchTableKind(presentation, model.series.length);
  const unitName = findUnitNameById(item.unit) || '';
  const enumUnit = isStringArray(item.unit);

  const formatValue = useCallback((value: number | null) => {
    if (value === null || !Number.isFinite(value)) return '--';
    if (enumUnit && item.metric) {
      return String(getEnumValue({ ...item.metric, unit: item.unit }, value));
    }
    const text = value.toFixed(2);
    return unitName ? `${text} ${unitName}` : text;
  }, [enumUnit, item.metric, item.unit, unitName]);

  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({});
  const [frozenSeriesKey, setFrozenSeriesKey] = useState<string | null>(null);
  const [headerMenu, setHeaderMenu] = useState<{
    seriesKey: string;
    x: number;
    y: number;
  } | null>(null);
  const columnWidth = (key: string, fallback: number) => columnWidths[key] ?? fallback;
  const resizeColumn = (key: string) => (nextWidth: number) => {
    setColumnWidths((prev) => ({ ...prev, [key]: nextWidth }));
  };
  const headerProps = (
    key: string,
    fallback: number,
    extra?: SearchHeaderCellProps
  ) => {
    const props: SearchHeaderCellProps = {
      ...extra,
      width: columnWidth(key, fallback),
      resizeHandler: resizeColumn(key)
    };
    return props;
  };

  const formatRange = useCallback((row: SearchSeriesRow) => {
    if (enumUnit || row.range === null) return '—';
    return formatValue(row.range);
  }, [enumUnit, formatValue]);

  const setView = (view: SearchChartView) => {
    onPresentationChange({ ...presentation, view });
  };

  const setTableKind = (kind: SearchTableKind) => {
    onPresentationChange({ ...presentation, tableKind: kind });
  };

  const emphasize = useCallback((key: string) => {
    onPresentationChange({
      ...presentation,
      emphasizedKeys: toggleEmphasizedSeries(presentation.emphasizedKeys, key)
    });
  }, [onPresentationChange, presentation]);

  const activateAllSeries = useCallback(() => {
    onPresentationChange({ ...presentation, emphasizedKeys: null });
  }, [onPresentationChange, presentation]);

  const deactivateAllSeries = useCallback(() => {
    onPresentationChange({ ...presentation, emphasizedKeys: [] });
  }, [onPresentationChange, presentation]);

  const exportCsv = () => {
    let headers: string[];
    let rows: string[][];
    if (tableKind === 'compare') {
      headers = [
        t('monitor.search.identifier'),
        t('monitor.search.latest'),
        t('monitor.search.min'),
        t('monitor.search.max'),
        t('monitor.search.avg'),
        t('monitor.search.range')
      ];
      rows = model.series.map((row) => [
        row.identifier,
        formatValue(row.latest),
        formatValue(row.min),
        formatValue(row.max),
        formatValue(row.avg),
        formatRange(row)
      ]);
    } else {
      headers = [
        t('monitor.search.time'),
        ...model.series.map((series) => series.identifier)
      ];
      rows = model.times
        .map((time, index) => [
          formatTime(time, minTime, maxTime),
          ...model.series.map((series) => formatValue(series.values[index]))
        ])
        .reverse();
    }
    const csv = toCsv(headers, rows);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const safeName = [
      item.aggregation,
      item.objectName,
      item.metric?.display_name || 'metric'
    ]
      .join('-')
      .replace(/[\\/:*?"<>|]/g, '_');
    link.href = url;
    link.download = `${safeName}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const chartHeight =
    layoutMode === 'double'
      ? presentation.view === 'combo'
        ? 'h-[150px]'
        : 'h-[220px]'
      : presentation.view === 'combo'
        ? 'h-[180px]'
        : 'h-[280px]';

  const compareColumns = useMemo<ColumnsType<SearchSeriesRow>>(() => [
    {
      title: (
        <SeriesActivationHeader
          label={t('monitor.search.identifier')}
          emphasizedKeys={presentation.emphasizedKeys}
          activateLabel={t('monitor.search.activateAll')}
          deactivateLabel={t('monitor.search.deactivateAll')}
          onActivateAll={activateAllSeries}
          onDeactivateAll={deactivateAllSeries}
        />
      ),
      dataIndex: 'identifier',
      width: columnWidth('identifier', 320),
      onHeaderCell: () => headerProps('identifier', 320),
      sorter: (left, right) => left.identifier.localeCompare(right.identifier),
      render: (_, row) => {
        const active = isSearchSeriesActive(presentation.emphasizedKeys, row.key);
        return (
          <div className="flex min-w-0 items-center gap-2">
            <span
              data-series-key={row.key}
              data-series-active={active ? 'true' : 'false'}
              className="h-1.5 w-4 flex-shrink-0 rounded-[1px] border border-solid"
              style={
                active
                  ? {
                    background: seriesColor[row.key],
                    borderColor: seriesColor[row.key]
                  }
                  : { borderColor: seriesColor[row.key] }
              }
            />
            <EllipsisWithTooltip text={row.identifier} className="min-w-0 truncate" />
          </div>
        );
      }
    },
    {
      title: t('monitor.search.latest'),
      dataIndex: 'latest',
      width: columnWidth('latest', 110),
      onHeaderCell: () => headerProps('latest', 110),
      sorter: (left, right) => (left.latest ?? Number.NEGATIVE_INFINITY) - (right.latest ?? Number.NEGATIVE_INFINITY),
      render: (_, row) => {
        const text = formatValue(row.latest);
        if (enumUnit) return text;
        return stainedValue(
          text,
          toneForExtreme(row.latest, model.series.map((series) => series.latest))
        );
      }
    },
    {
      title: t('monitor.search.min'),
      dataIndex: 'min',
      width: columnWidth('min', 100),
      onHeaderCell: () => headerProps('min', 100),
      sorter: (left, right) => (left.min ?? Number.NEGATIVE_INFINITY) - (right.min ?? Number.NEGATIVE_INFINITY),
      render: (_, row) => formatValue(row.min)
    },
    {
      title: t('monitor.search.max'),
      dataIndex: 'max',
      width: columnWidth('max', 100),
      onHeaderCell: () => headerProps('max', 100),
      sorter: (left, right) => (left.max ?? Number.NEGATIVE_INFINITY) - (right.max ?? Number.NEGATIVE_INFINITY),
      render: (_, row) => formatValue(row.max)
    },
    {
      title: t('monitor.search.avg'),
      dataIndex: 'avg',
      width: columnWidth('avg', 100),
      onHeaderCell: () => headerProps('avg', 100),
      sorter: (left, right) => (left.avg ?? Number.NEGATIVE_INFINITY) - (right.avg ?? Number.NEGATIVE_INFINITY),
      render: (_, row) => formatValue(row.avg)
    },
    {
      title: t('monitor.search.range'),
      dataIndex: 'range',
      width: columnWidth('range', 100),
      onHeaderCell: () => headerProps('range', 100),
      defaultSortOrder: 'descend',
      sorter: (left, right) => (left.range ?? Number.NEGATIVE_INFINITY) - (right.range ?? Number.NEGATIVE_INFINITY),
      render: (_, row) => {
        const text = formatRange(row);
        if (enumUnit) return text;
        return stainedValue(
          text,
          toneForExtreme(row.range, model.series.map((series) => series.range))
        );
      }
    },
    {
      title: t('monitor.search.trend'),
      width: columnWidth('trend', 88),
      onHeaderCell: () => headerProps('trend', 88),
      render: (_, row) => (
        <Sparkline
          values={row.values}
          color={seriesColor[row.key]}
        />
      )
    }
  ], [columnWidths, enumUnit, formatRange, formatValue, model.series, presentation, seriesColor, t]);

  const compareTable = (
    <Table<SearchSeriesRow>
      size="small"
      rowKey="key"
      pagination={false}
      columns={compareColumns}
      dataSource={model.series}
      components={{ header: { cell: SearchTableHeaderCell } }}
      className="[&_tbody_tr]:cursor-pointer"
      scroll={{
        x: compareColumns.reduce(
          (sum, column) => sum + (typeof column.width === 'number' ? column.width : 0),
          0
        ),
        y: 280
      }}
      rowClassName={(row) =>
        presentation.emphasizedKeys?.includes(row.key) ? 'ant-table-row-selected' : ''
      }
      onRow={(row) => ({
        onClick: () => emphasize(row.key)
      })}
      locale={{
        emptyText: (
          <CompactEmptyState description={t('monitor.search.emptySeries')} />
        )
      }}
    />
  );

  const minTime = model.times[0] ?? 0;
  const maxTime = model.times[model.times.length - 1] ?? 0;
  const sampleSeries = placeFrozenSampleSeries(model.series, frozenSeriesKey);
  const sampleColumns: ColumnsType<{ time: number; index: number }> = [
    {
      title: t('monitor.search.time'),
      dataIndex: 'time',
      width: columnWidth('time', 160),
      fixed: 'left',
      onHeaderCell: () => headerProps('time', 160, { 'data-column-key': 'time' }),
      render: (time: number) => formatTime(time, minTime, maxTime)
    },
    ...sampleSeries.map((series) => ({
      title: (
        <EllipsisWithTooltip
          text={series.identifier}
          className="block w-full truncate"
        />
      ),
      dataIndex: series.key,
      width: columnWidth(series.key, 320),
      fixed: series.key === frozenSeriesKey ? ('left' as const) : undefined,
      onHeaderCell: () =>
        headerProps(series.key, 320, {
          'data-column-key': series.key,
          onContextMenu: (event) => {
            event.preventDefault();
            setHeaderMenu({
              seriesKey: series.key,
              x: event.clientX,
              y: event.clientY
            });
          }
        }),
      render: (_: unknown, row: { index: number }) => {
        const value = series.values[row.index];
        const text = formatValue(value);
        if (enumUnit) return text;
        return stainedValue(text, toneForExtreme(value, series.values));
      }
    }))
  ];
  const sampleRows = model.times
    .map((time, index) => ({ time, index }))
    .reverse();

  const sampleTable = (
    <Table
      size="small"
      rowKey="time"
      pagination={false}
      columns={sampleColumns}
      dataSource={sampleRows}
      components={{ header: { cell: SearchTableHeaderCell } }}
      scroll={{
        x: sampleColumns.reduce(
          (sum, column) => sum + (typeof column.width === 'number' ? column.width : 0),
          0
        ),
        y: 280
      }}
      locale={{
        emptyText: (
          <CompactEmptyState description={t('monitor.search.emptySeries')} />
        )
      }}
    />
  );

  const chart = (
    <div className={chartHeight}>
      <LineChart
        metric={item.metric || undefined}
        data={item.data}
        unit={item.unit}
        showDimensionTable={
          presentation.view === 'line' && layoutMode === 'single'
        }
        emphasizedKeys={presentation.emphasizedKeys}
        onEmphasizedKeyChange={emphasize}
        onActivateAllSeries={activateAllSeries}
        onDeactivateAllSeries={deactivateAllSeries}
        key={layoutMode}
        syncId="monitor-search-charts"
        onXRangeChange={onXRangeChange}
      />
    </div>
  );

  const tableToolbar = (
    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
      <Segmented
        size="small"
        value={tableKind}
        onChange={(value) => setTableKind(value as SearchTableKind)}
        options={[
          { label: t('monitor.search.seriesCompare'), value: 'compare' },
          { label: t('monitor.search.sampleDetail'), value: 'samples' }
        ]}
      />
      <Button size="small" icon={<DownloadOutlined />} onClick={exportCsv}>
        {t('monitor.search.exportCsv')}
      </Button>
    </div>
  );

  const body =
    presentation.view === 'combo' ? (
      <div>
        {chart}
        <div className="mt-2">
          {tableToolbar}
          {tableKind === 'compare' ? compareTable : sampleTable}
        </div>
      </div>
    ) : (
      chart
    );

  const titleUnit = unitName ? `（${unitName}）` : '';

  const headerMenuSeries = headerMenu
    ? sampleSeries.find((series) => series.key === headerMenu.seriesKey)
    : null;

  return (
    <>
    {headerMenu && headerMenuSeries ? (
      <Dropdown
        open
        trigger={['click']}
        menu={{
          items: [
            frozenSeriesKey === headerMenu.seriesKey
              ? { key: 'unpin', label: t('monitor.search.unpinColumn') }
              : { key: 'pin', label: t('monitor.search.pinColumn') }
          ],
          onClick: ({ key }) => {
            setFrozenSeriesKey(key === 'unpin' ? null : headerMenu.seriesKey);
            setHeaderMenu(null);
          }
        }}
        onOpenChange={(open) => {
          if (!open) setHeaderMenu(null);
        }}
      >
        <span
          className="fixed z-[80] h-px w-px"
          style={{ left: headerMenu.x, top: headerMenu.y }}
        />
      </Dropdown>
    ) : null}
    <Card
      size="small"
      style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}
      title={
        <div className="flex items-start gap-3 min-w-0">
          <div className="min-w-0 flex-1 overflow-hidden">
            <div className="flex items-center min-w-0">
              <EllipsisWithTooltip
                text={`${item.aggregation}(${item.objectName}-${item.metric?.display_name || '--'})`}
                className="font-medium truncate max-w-full"
              />
              {titleUnit ? (
                <span className="flex-shrink-0 text-[12px] font-medium text-[var(--color-text-3)]">
                  {titleUnit}
                </span>
              ) : null}
            </div>
            {item.metric?.display_description ? (
              <div
                className="mt-[2px] line-clamp-2 text-[12px] leading-[18px] text-[var(--color-text-3)]"
                title={item.metric.display_description}
              >
                {item.metric.display_description}
              </div>
            ) : null}
          </div>
          <div className="flex flex-shrink-0 flex-col items-end gap-1">
            {!item.loading && item.duration > 0 && (
              <span className="whitespace-nowrap text-xs font-normal text-[var(--color-text-3)]">
                {t('monitor.search.duration')} {item.duration}
                {t('monitor.search.ms')}
              </span>
            )}
            <Segmented
              size="small"
              value={presentation.view}
              onChange={(value) => setView(value as SearchChartView)}
              options={[
                { label: t('monitor.search.line'), value: 'line' },
                { label: t('monitor.search.combo'), value: 'combo' }
              ]}
            />
            {showApplyAll && (
              <Tooltip title={t('monitor.search.applyAllTip')}>
                <Button
                  type="text"
                  size="small"
                  className="h-auto px-1 text-[var(--color-text-3)]"
                  icon={<CopyOutlined />}
                  aria-label={t('monitor.search.applyAll')}
                  onClick={onApplyAll}
                />
              </Tooltip>
            )}
          </div>
        </div>
      }
      loading={item.loading}
      styles={{
        header: { alignItems: 'flex-start', height: 'auto' },
        title: { overflow: 'visible', whiteSpace: 'normal' },
        body: { padding: '12px' }
      }}
    >
      {body}
    </Card>
    </>
  );
};

export default SearchResultCard;
