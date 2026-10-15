import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

import { buildCsvDocument, buildCsvFilename, escapeCsvCell } from '@/app/ops-analysis/utils/csvDocument';
import {
  buildDashboardWidgetMenuKeys,
  resolveScreenItemMenuMode,
  resolveTopologyCsvExportHoverEnabled,
  resolveWidgetCsvExportEntry,
  type WidgetCsvExportSurface,
} from '@/app/ops-analysis/utils/widgetCsvMenu';
import {
  CSV_EXPORT_ROW_LIMIT,
  buildLineBarCsvTable,
  buildMultiValueCsvTable,
  buildPieCsvTable,
  buildRadarCsvTable,
  buildTableCsvTable,
  buildTopNCsvTable,
  buildWidgetCsvLabels,
  createWidgetCsvExport,
  describeWidgetCsvExportNotice,
  loadTableExportRows,
  supportsWidgetCsvExport,
  type WidgetCsvLabels,
} from '@/app/ops-analysis/utils/widgetCsvExport';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';

const labels: WidgetCsvLabels = {
  time: '时间',
  dimension: '维度',
  value: '数值',
  indicator: '指标',
  name: '名称',
  seriesValue: '数据值',
};

const schema = [
  { key: 'ts', title: '采集时间', value_type: 'datetime' as const },
  { key: 'cpu', title: 'CPU 使用率', value_type: 'number' as const },
  { key: 'host', title: '主机', value_type: 'string' as const },
  { key: 'metric', title: '指标名', value_type: 'string' as const },
];

describe('csv escaping', () => {
  it('adds a UTF-8 BOM, CRLF rows, and quotes commas, quotes, and newlines', () => {
    const csv = buildCsvDocument(
      ['名称', '说明'],
      [['普通', '含,逗号'], ['引"号', '第一行\n第二行']],
    );
    expect(csv.startsWith('\uFEFF')).toBe(true);
    expect(csv).toBe('\uFEFF名称,说明\r\n普通,"含,逗号"\r\n"引""号","第一行\n第二行"');
  });

  it('prefixes formula-leading cells so Excel treats them as text', () => {
    expect(escapeCsvCell('=1+1')).toBe("'=1+1");
    expect(escapeCsvCell('+cmd')).toBe("'+cmd");
    expect(escapeCsvCell('-2')).toBe('-2');
    expect(escapeCsvCell('-3.5')).toBe('-3.5');
    expect(escapeCsvCell('-1.5%')).toBe('-1.5%');
    expect(escapeCsvCell('-2+3')).toBe("'-2+3");
    expect(escapeCsvCell('@sum')).toBe("'@sum");
    expect(escapeCsvCell(' =1+1')).toBe("' =1+1");
    expect(escapeCsvCell('安全')).toBe('安全');
    const csv = buildCsvDocument(['值'], [['=HYPERLINK("http://evil")']]);
    expect(csv).toContain(`"'=HYPERLINK(""http://evil"")"`);
  });

  it('names the file with the widget title and a user-timezone timestamp', () => {
    window.localStorage.setItem('timezone', 'Asia/Shanghai');
    expect(buildCsvFilename('CPU 使用率', new Date('2026-03-01T00:30:00Z'))).toBe(
      'CPU 使用率-20260301-083000.csv',
    );
    expect(buildCsvFilename('a/b:c', new Date('2026-03-01T00:30:00Z'))).toBe(
      'a_b_c-20260301-083000.csv',
    );
  });
});

describe('widget csv rows', () => {
  it('turns a multi-series line into a time column plus one column per series', () => {
    window.localStorage.setItem('timezone', 'Asia/Shanghai');
    const table = buildLineBarCsvTable(
      {
        入站: [[1700000000, 1.5], [1700003600, 2]],
        出站: [[1700000000, 3], [1700003600, 4]],
      },
      { unitId: 'percent' },
      labels,
    );
    expect(table.headers).toEqual(['时间', '入站 (%)', '出站 (%)']);
    expect(table.rows).toEqual([
      ['11-15 06:13', '1.5%', '3%'],
      ['11-15 07:13', '2%', '4%'],
    ]);
  });

  it('uses the configured field alias for a single bar series', () => {
    const table = buildLineBarCsvTable(
      [{ host: '主机甲', cpu: 12 }],
      { dimensionField: 'host', valueField: 'cpu', unit: '核' },
      labels,
      schema,
    );
    expect(table.headers).toEqual(['主机', 'CPU 使用率 (核)']);
    expect(table.rows).toEqual([['主机甲', '12核']]);
  });

  it('exports pie slices with the dimension and value headers', () => {
    const table = buildPieCsvTable(
      [{ name: '华东', value: 2 }, { name: '华南', value: 3 }],
      { unitId: 'short' },
      labels,
    );
    expect(table.headers).toEqual(['维度', '数值']);
    expect(table.rows).toEqual([
      ['华东', '2'],
      ['华南', '3'],
    ]);
  });

  it('exports TopN with the on-screen field titles', () => {
    const table = buildTopNCsvTable(
      [{ host: 'db-1', cpu: 80 }],
      { topNLabelField: 'host', topNValueField: 'cpu', unitId: 'percent' },
      labels,
      schema,
    );
    expect(table.headers[0]).toContain('主机');
    expect(table.headers[1]).toContain('CPU 使用率');
    expect(table.rows).toEqual([['db-1', '80%']]);
  });

  it('exports radar indicators as rows', () => {
    const table = buildRadarCsvTable(
      { latency: 12, error: 3 },
      {
        unit: 'ms',
        radar: {
          indicators: [
            { key: 'latency', label: '延迟' },
            { key: 'error', label: '错误数' },
          ],
        },
      },
      labels,
    );
    expect(table.headers).toEqual(['指标', '数值']);
    expect(table.rows).toEqual([
      ['延迟', '12 ms'],
      ['错误数', '3 ms'],
    ]);
  });

  it('does not build a multi-series radar table', () => {
    const table = buildRadarCsvTable(
      {
        hostA: [
          { name: 'CPU', value: 70 },
          { name: 'Memory', value: 55 },
        ],
        hostB: [
          { name: 'CPU', value: 60 },
          { name: 'Memory', value: 48 },
        ],
      },
      { unit: 'ms' },
      labels,
    );
    expect(table.rows).toEqual([]);
  });

  it('exports multi-value rows with aliases and formatted values', () => {
    const table = buildMultiValueCsvTable(
      [{ metric: '可用率', cpu: 99 }],
      { multiValueLabelField: 'metric', multiValueValueField: 'cpu', unitId: 'percent' },
      labels,
      schema,
    );
    expect(table.headers).toEqual(['指标名', 'CPU 使用率 (%)']);
    expect(table.rows).toEqual([['可用率', '99%']]);
  });

  it('exports the filtered table, not only the current page, and skips action columns', () => {
    const config: ValueConfig = {
      tableConfig: {
        columns: [
          { key: 'host', title: '主机名', visible: true, order: 0 },
          { key: 'status', title: '状态', visible: true, order: 1, valueMappings: [{ type: 'value', value: 'up', result: { text: '正常' } }] },
          { key: 'ops', title: '操作', visible: true, order: 2, columnType: 'actions' },
          { key: 'hidden', title: '隐藏', visible: false, order: 3 },
        ],
      },
    };
    const rows = [
      { host: '甲', status: 'up', ops: 'go', hidden: 'x' },
      { host: '乙', status: 'down', ops: 'go', hidden: 'y' },
    ];
    const table = buildTableCsvTable('table', rows, config, undefined);
    expect(table.headers).toEqual(['主机名', '状态']);
    expect(table.rows).toEqual([
      ['甲', '正常'],
      ['乙', 'down'],
    ]);
  });

  it('keeps event table headers to the configured columns', () => {
    const table = buildTableCsvTable(
      'eventTable',
      [{ title: '告警', level: null }],
      {
        tableConfig: {
          columns: [
            { key: 'title', title: '事件标题', visible: true, order: 1 },
            { key: 'level', title: '级别', visible: true, order: 0 },
          ],
        },
      },
      undefined,
    );
    expect(table.headers).toEqual(['级别', '事件标题']);
    expect(table.rows).toEqual([['-', '告警']]);
  });
});

describe('table export limit', () => {
  it('reuses the current result when it already contains every filtered row', async () => {
    const fetchPage = vi.fn();
    const loaded = await loadTableExportRows({
      rawData: [{ name: '甲' }, { name: '乙' }, { name: '丙' }],
      supportsPagination: false,
      queryList: [{ field: 'name', type: 'str*', value: '甲' }],
      fetchPage,
    });
    expect(fetchPage).not.toHaveBeenCalled();
    expect(loaded.rows).toEqual([{ name: '甲' }]);
    expect(loaded.truncated).toBe(false);
  });

  it('refetches with the same filters when the table is server-paginated and stops at the cap', async () => {
    const calls: Array<Record<string, unknown>> = [];
    const all = Array.from({ length: 1200 }, (_, index) => ({ name: `主机${index}` }));
    const loaded = await loadTableExportRows({
      rawData: { items: all.slice(0, 20), count: 1200 },
      supportsPagination: true,
      queryList: [],
      fetchPage: async (page, pageSize) => {
        calls.push({ page, pageSize });
        const start = (page - 1) * pageSize;
        return { items: all.slice(start, start + pageSize), count: all.length };
      },
    });
    expect(calls[0]).toEqual({ page: 1, pageSize: CSV_EXPORT_ROW_LIMIT });
    expect(loaded.rows).toHaveLength(CSV_EXPORT_ROW_LIMIT);
    expect(loaded.rows[0]).toEqual({ name: '主机0' });
    expect(loaded.truncated).toBe(true);
  });

  it('pages with the size the server actually returned when a large page is capped', async () => {
    const calls: number[] = [];
    const all = Array.from({ length: 250 }, (_, index) => ({ name: `row-${index}` }));
    const loaded = await loadTableExportRows({
      rawData: { items: all.slice(0, 20), count: 250 },
      supportsPagination: true,
      queryList: [{ field: 'name', type: 'str*', value: 'row-1' }],
      fetchPage: async (page, pageSize) => {
        calls.push(pageSize);
        if (page === 1 && pageSize === CSV_EXPORT_ROW_LIMIT) {
          return { items: all.slice(0, 100), count: 250, page_size: 100 };
        }
        const start = (page - 1) * pageSize;
        return { items: all.slice(start, start + pageSize), count: 250, page_size: pageSize };
      },
    });
    expect(calls).toEqual([1000, 100, 100]);
    expect(loaded.rows.map((row) => row.name)).toEqual(['row-1', 'row-10', 'row-11', 'row-12', 'row-13', 'row-14', 'row-15', 'row-16', 'row-17', 'row-18', 'row-19', 'row-100', 'row-101', 'row-102', 'row-103', 'row-104', 'row-105', 'row-106', 'row-107', 'row-108', 'row-109', 'row-110', 'row-111', 'row-112', 'row-113', 'row-114', 'row-115', 'row-116', 'row-117', 'row-118', 'row-119', 'row-120', 'row-121', 'row-122', 'row-123', 'row-124', 'row-125', 'row-126', 'row-127', 'row-128', 'row-129', 'row-130', 'row-131', 'row-132', 'row-133', 'row-134', 'row-135', 'row-136', 'row-137', 'row-138', 'row-139', 'row-140', 'row-141', 'row-142', 'row-143', 'row-144', 'row-145', 'row-146', 'row-147', 'row-148', 'row-149', 'row-150', 'row-151', 'row-152', 'row-153', 'row-154', 'row-155', 'row-156', 'row-157', 'row-158', 'row-159', 'row-160', 'row-161', 'row-162', 'row-163', 'row-164', 'row-165', 'row-166', 'row-167', 'row-168', 'row-169', 'row-170', 'row-171', 'row-172', 'row-173', 'row-174', 'row-175', 'row-176', 'row-177', 'row-178', 'row-179', 'row-180', 'row-181', 'row-182', 'row-183', 'row-184', 'row-185', 'row-186', 'row-187', 'row-188', 'row-189', 'row-190', 'row-191', 'row-192', 'row-193', 'row-194', 'row-195', 'row-196', 'row-197', 'row-198', 'row-199']);
    expect(loaded.truncated).toBe(false);
  });

  it('keeps the requested page size when search filters rows inside the page', async () => {
    const calls: number[] = [];
    const all = Array.from({ length: 1500 }, (_, index) => ({
      name: index % 50 === 0 ? `hit-${index}` : `row-${index}`,
    }));
    const loaded = await loadTableExportRows({
      rawData: { items: all.slice(0, 20).filter((row) => row.name.startsWith('hit-')), count: 1500 },
      supportsPagination: true,
      queryList: [{ field: 'name', type: 'str*', value: 'hit-' }],
      fetchPage: async (page, pageSize) => {
        calls.push(pageSize);
        const start = (page - 1) * pageSize;
        const window = all.slice(start, start + pageSize);
        return {
          items: window.filter((row) => row.name.startsWith('hit-')),
          count: all.length,
        };
      },
    });
    expect(calls).toEqual([CSV_EXPORT_ROW_LIMIT, CSV_EXPORT_ROW_LIMIT]);
    expect(loaded.rows).toHaveLength(30);
    expect(loaded.rows[0]).toEqual({ name: 'hit-0' });
    expect(loaded.rows[29]).toEqual({ name: 'hit-1450' });
    expect(loaded.truncated).toBe(false);
  });

  it('refetches a plain array at the export cap and warns when that cap is filled', async () => {
    const calls: number[] = [];
    const capped = await loadTableExportRows({
      rawData: [{ name: 'page-only' }],
      supportsPagination: true,
      queryList: [],
      fetchPage: async (_page, pageSize) => {
        calls.push(pageSize);
        return Array.from({ length: pageSize }, (_, index) => ({ name: `r${index}` }));
      },
    });
    expect(calls).toEqual([CSV_EXPORT_ROW_LIMIT]);
    expect(capped.rows).toHaveLength(CSV_EXPORT_ROW_LIMIT);
    expect(capped.rows[0]).toEqual({ name: 'r0' });
    expect(capped.truncated).toBe(true);

    const short = await loadTableExportRows({
      rawData: [{ name: 'page-only' }],
      supportsPagination: true,
      queryList: [],
      fetchPage: async () => [{ name: 'a' }, { name: 'b' }],
    });
    expect(short.rows).toEqual([{ name: 'a' }, { name: 'b' }]);
    expect(short.truncated).toBe(false);
  });

  it('pages with the returned length when a datasource caps page size without echoing it', async () => {
    const calls: number[] = [];
    const all = Array.from({ length: 250 }, (_, index) => ({ name: `row-${index}` }));
    const loaded = await loadTableExportRows({
      rawData: { items: all.slice(0, 20), count: 250 },
      supportsPagination: true,
      queryList: [],
      fetchPage: async (page, pageSize) => {
        calls.push(pageSize);
        if (pageSize > 100) return { items: all.slice(0, 100), count: 250 };
        const start = (page - 1) * pageSize;
        return { items: all.slice(start, start + pageSize), count: 250 };
      },
    });
    expect(calls).toEqual([1000, 100, 100]);
    expect(loaded.rows).toHaveLength(250);
    expect(loaded.truncated).toBe(false);
  });

  it('follows the latest search conditions instead of an earlier page', async () => {
    const rows = [{ host: '上海' }, { host: '北京' }];
    const first = await loadTableExportRows({
      rawData: rows,
      supportsPagination: false,
      queryList: [{ field: 'host', type: 'str*', value: '上' }],
    });
    const second = await loadTableExportRows({
      rawData: rows,
      supportsPagination: false,
      queryList: [{ field: 'host', type: 'str*', value: '北' }],
    });
    expect(first.rows).toEqual([{ host: '上海' }]);
    expect(second.rows).toEqual([{ host: '北京' }]);
  });

  it('says the first N rows were exported when the cap is hit', () => {
    const zh = JSON.parse(readFileSync(path.resolve('src/app/ops-analysis/locales/zh.json'), 'utf8')) as {
      dashboard: { csvExportTruncated: string };
    };
    expect(zh.dashboard.csvExportTruncated).toBe('已导出前 {count} 条');
    const notice = describeWidgetCsvExportNotice(
      {
        kind: 'truncated',
        csv: '',
        filename: 'a.csv',
        exportedCount: CSV_EXPORT_ROW_LIMIT,
        limit: CSV_EXPORT_ROW_LIMIT,
      },
      (id, _defaultMessage, values) => (
        id === 'dashboard.csvExportTruncated' ? `已导出前 ${values?.count} 条` : id
      ),
    );
    expect(notice).toEqual({ level: 'info', text: '已导出前 1000 条' });
    const shortPage = describeWidgetCsvExportNotice(
      {
        kind: 'truncated',
        csv: '',
        filename: 'a.csv',
        exportedCount: 100,
        limit: CSV_EXPORT_ROW_LIMIT,
      },
      (id, _defaultMessage, values) => (
        id === 'dashboard.csvExportTruncated' ? `已导出前 ${values?.count} 条` : id
      ),
    );
    expect(shortPage?.text).toBe('已导出前 100 条');
  });
});

describe('csv export entry', () => {
  it('shows export for supported charts and hides it for single, gauge, topology, and node graph', () => {
    expect(['table', 'eventTable', 'line', 'bar', 'pie', 'topN', 'radar', 'multiValue'].every(supportsWidgetCsvExport)).toBe(true);
    expect(['single', 'gauge', 'topologyMap', 'nodeGraph', 'room3D', 'eventTimeline'].some(supportsWidgetCsvExport)).toBe(false);

    expect(buildDashboardWidgetMenuKeys({
      surface: 'dashboard',
      isEditMode: false,
      chartType: 'line',
    })).toEqual([]);
    expect(resolveWidgetCsvExportEntry({
      surface: 'dashboard',
      chartType: 'line',
      editMode: false,
    })).toBe('hover');
    const multiSeriesRadar = {
      hostA: [{ name: 'CPU', value: 70 }],
      hostB: [{ name: 'CPU', value: 60 }],
    };
    expect(resolveWidgetCsvExportEntry({
      surface: 'dashboard',
      chartType: 'radar',
      editMode: false,
      rawData: multiSeriesRadar,
    })).toBe('none');
    expect(resolveWidgetCsvExportEntry({
      surface: 'report',
      chartType: 'radar',
      editMode: true,
      rawData: multiSeriesRadar,
    })).toBe('none');
    expect(buildDashboardWidgetMenuKeys({
      surface: 'dashboard',
      isEditMode: true,
      chartType: 'radar',
      rawData: multiSeriesRadar,
    })).toEqual(['edit', 'copy', 'delete']);
    expect(buildDashboardWidgetMenuKeys({
      surface: 'report',
      isEditMode: true,
      chartType: 'radar',
      rawData: { latency: 1, error: 2 },
    })).toEqual(['edit', 'copy', 'exportCsv', 'delete']);
    expect(buildDashboardWidgetMenuKeys({
      surface: 'dashboard',
      isEditMode: true,
      chartType: 'table',
    })).toEqual(['edit', 'copy', 'exportCsv', 'delete']);
    expect(buildDashboardWidgetMenuKeys({
      surface: 'report',
      isEditMode: true,
      chartType: 'table',
    })).toEqual(['edit', 'copy', 'exportCsv', 'delete']);
    expect(buildDashboardWidgetMenuKeys({
      surface: 'dashboard',
      isEditMode: false,
      chartType: 'single',
    })).toEqual([]);
    expect(buildDashboardWidgetMenuKeys({
      surface: 'dashboard',
      isEditMode: true,
      chartType: 'gauge',
    })).toEqual(['edit', 'copy', 'delete']);
    expect(buildDashboardWidgetMenuKeys({
      surface: 'dashboard',
      isEditMode: true,
      chartType: 'nodeGraph',
    })).toEqual(['edit', 'copy', 'delete']);
    expect(buildDashboardWidgetMenuKeys({
      surface: 'dashboard',
      isEditMode: true,
      shareMode: true,
      chartType: 'pie',
    })).toEqual(['edit', 'delete']);
    expect(buildDashboardWidgetMenuKeys({
      surface: 'dashboard',
      isEditMode: false,
      renderMode: true,
      chartType: 'line',
    })).toEqual([]);
    expect(resolveScreenItemMenuMode({ editMode: false, shareMode: true })).toBe('view');
    expect(resolveScreenItemMenuMode({ editMode: true })).toBe('edit');
    expect(resolveScreenItemMenuMode({ editMode: true, fullscreen: true })).toBe('view');
  });

  it('keeps export off the canvas in fullscreen, share, and screenshot modes', () => {
    const surfaces: WidgetCsvExportSurface[] = ['dashboard', 'screen', 'topology', 'report'];
    const supported = ['table', 'eventTable', 'line', 'bar', 'pie', 'topN', 'radar', 'multiValue'];
    const blocked = ['single', 'gauge', 'topologyMap', 'nodeGraph'];
    surfaces.forEach((surface) => {
      supported.forEach((chartType) => {
        expect(resolveWidgetCsvExportEntry({ surface, chartType, editMode: false })).toBe(
          surface === 'screen' ? 'none' : 'hover',
        );
        expect(resolveWidgetCsvExportEntry({ surface, chartType, editMode: true })).toBe('menu');
        expect(resolveWidgetCsvExportEntry({ surface, chartType, editMode: false, fullscreen: true })).toBe('none');
        expect(resolveWidgetCsvExportEntry({ surface, chartType, editMode: true, fullscreen: true })).toBe('none');
        expect(resolveWidgetCsvExportEntry({ surface, chartType, editMode: false, shareMode: true })).toBe('none');
        expect(resolveWidgetCsvExportEntry({ surface, chartType, editMode: true, shareMode: true })).toBe('none');
        expect(resolveWidgetCsvExportEntry({ surface, chartType, editMode: false, renderMode: true })).toBe('none');
        expect(resolveWidgetCsvExportEntry({ surface, chartType, editMode: true, renderMode: true })).toBe('none');
      });
      blocked.forEach((chartType) => {
        expect(resolveWidgetCsvExportEntry({ surface, chartType, editMode: false })).toBe('none');
        expect(resolveWidgetCsvExportEntry({ surface, chartType, editMode: true })).toBe('none');
      });
    });
    expect(resolveTopologyCsvExportHoverEnabled({ editMode: false })).toBe(true);
    expect(resolveTopologyCsvExportHoverEnabled({ editMode: true })).toBe(false);
    expect(resolveTopologyCsvExportHoverEnabled({ editMode: false, shareMode: true })).toBe(false);
    expect(resolveTopologyCsvExportHoverEnabled({ editMode: false, fullscreen: true })).toBe(false);
  });

  it('builds a downloadable csv from the current line result and refuses unsupported charts', async () => {
    const exported = await createWidgetCsvExport(
      {
        chartType: 'line',
        rawData: [{ name: '周一', value: 1 }],
        loading: false,
      },
      { title: '趋势', now: new Date('2026-03-01T00:30:00Z') },
      buildWidgetCsvLabels((id) => ({
        'dashboard.csvTime': '时间',
        'dashboard.dimensionField': '维度',
        'dashboard.valueField': '数值',
        'dashboard.csvIndicator': '指标',
        'dashboard.csvName': '名称',
        'topology.treeValueTitle': '数据值',
      }[id] || id)),
    );
    expect(exported.kind).toBe('downloaded');
    if (exported.kind !== 'downloaded') return;
    expect(exported.filename.startsWith('趋势-')).toBe(true);
    expect(exported.csv.startsWith('\uFEFF维度,数据值')).toBe(true);
    expect(exported.csv).toContain('周一,1');

    const blocked = await createWidgetCsvExport(
      { chartType: 'single', rawData: { value: 1 } },
      { title: '单值' },
      labels,
    );
    expect(blocked.kind).toBe('unsupported');
  });

  it('keeps the widget request filters when loading the full table', async () => {
    const seen: Record<string, unknown>[] = [];
    const outcome = await createWidgetCsvExport(
      {
        chartType: 'table',
        rawData: { items: [{ host: '当前页' }], count: 2 },
        loading: false,
        dataSourceId: 7,
        dataSource: {
          params: [
            { name: 'page', type: 'number' },
            { name: 'page_size', type: 'number' },
          ],
        } as never,
        requestParams: {
          page: 2,
          page_size: 20,
          query_list: [{ field: 'host', type: 'str*', value: '上海' }],
          time_range: ['2026-03-01T00:00:00Z', '2026-03-02T00:00:00Z'],
        },
        tableQueryParams: {
          query_list: [{ field: 'host', type: 'str*', value: '上海' }],
        },
        fetchSourceData: async (params) => {
          seen.push(params);
          return {
            items: [{ host: '上海-1' }, { host: '北京' }],
            count: 2,
          };
        },
      },
      { title: '主机表', now: new Date('2026-03-01T00:30:00Z') },
      labels,
    );
    expect(seen[0]).toMatchObject({
      page: 1,
      page_size: CSV_EXPORT_ROW_LIMIT,
      time_range: ['2026-03-01T00:00:00Z', '2026-03-02T00:00:00Z'],
      query_list: [{ field: 'host', type: 'str*', value: '上海' }],
    });
    expect(outcome.kind).toBe('downloaded');
    if (outcome.kind !== 'downloaded') return;
    expect(outcome.csv).toContain('上海-1');
    expect(outcome.csv).not.toContain('北京');
    expect(outcome.csv).not.toContain('当前页');
  });

  it('aborts when filters change while later pages are loading', async () => {
    let query = '上海';
    const seen: number[] = [];
    const runtime = {
      chartType: 'table' as const,
      rawData: { items: [{ host: '上海-1' }], count: 3 },
      loading: false,
      dataSourceId: 7,
      dataSource: {
        params: [
          { name: 'page', type: 'number' },
          { name: 'page_size', type: 'number' },
        ],
      } as never,
      requestParams: {
        page: 1,
        page_size: 20,
        query_list: [{ field: 'host', type: 'str*', value: query }],
      },
      tableQueryParams: {
        query_list: [{ field: 'host', type: 'str*', value: query }],
      },
      fetchSourceData: async (params: Record<string, unknown>) => {
        seen.push(Number(params.page));
        if (params.page === 1) query = '北京';
        return {
          items: [{ host: `${query}-p${params.page}` }],
          count: 3,
          page_size: 1,
        };
      },
    };
    const outcome = await createWidgetCsvExport(
      runtime,
      { title: '主机表' },
      labels,
      CSV_EXPORT_ROW_LIMIT,
      {
        readLatest: () => ({
          ...runtime,
          requestParams: {
            ...runtime.requestParams,
            query_list: [{ field: 'host', type: 'str*', value: query }],
          },
          tableQueryParams: {
            query_list: [{ field: 'host', type: 'str*', value: query }],
          },
        }),
      },
    );
    expect(seen).toEqual([1]);
    expect(outcome.kind).toBe('stale');
    const notice = describeWidgetCsvExportNotice(
      outcome,
      (id) => (id === 'dashboard.csvExportStale' ? '筛选条件已变化，已取消本次导出' : id),
    );
    expect(notice).toEqual({ level: 'warning', text: '筛选条件已变化，已取消本次导出' });
  });

  it('keeps exporting when only the table page changes', async () => {
    let page = 1;
    const query = [{ field: 'host', type: 'str*', value: '上海' }];
    const runtime = {
      chartType: 'table' as const,
      rawData: { items: [{ host: '上海-1' }], count: 2 },
      loading: false,
      dataSourceId: 7,
      dataSource: {
        params: [
          { name: 'page', type: 'number' },
          { name: 'page_size', type: 'number' },
        ],
      } as never,
      requestParams: { page: 1, page_size: 20, query_list: query },
      tableQueryParams: { page: 1, page_size: 20, query_list: query },
      fetchSourceData: async () => {
        page = 2;
        return {
          items: [{ host: '上海-1' }],
          count: 2,
          page_size: 1,
        };
      },
    };
    const outcome = await createWidgetCsvExport(
      runtime,
      { title: '主机表' },
      labels,
      CSV_EXPORT_ROW_LIMIT,
      {
        readLatest: () => ({
          ...runtime,
          loading: true,
          requestParams: { page, page_size: 20, query_list: query },
          tableQueryParams: { page, page_size: 20, query_list: query },
        }),
      },
    );
    expect(outcome.kind).toBe('downloaded');
  });

  it('keeps a topology export going when only the table page changes', async () => {
    let page = 1;
    const query = [{ field: 'host', type: 'str*', value: '上海' }];
    const runtime = {
      chartType: 'table' as const,
      rawData: { items: [{ host: '上海-1' }], count: 2 },
      loading: false,
      requestGeneration: 3,
      dataSourceId: 7,
      dataSource: {
        params: [
          { name: 'page', type: 'number' },
          { name: 'page_size', type: 'number' },
        ],
      } as never,
      requestParams: { page: 1, page_size: 20, query_list: query },
      tableQueryParams: { page: 1, page_size: 20, query_list: query },
      fetchSourceData: async () => {
        page = 2;
        return {
          items: [{ host: '上海-1' }],
          count: 2,
          page_size: 1,
        };
      },
    };
    const outcome = await createWidgetCsvExport(
      runtime,
      { title: '主机表' },
      labels,
      CSV_EXPORT_ROW_LIMIT,
      {
        readLatest: () => ({
          ...runtime,
          loading: true,
          requestGeneration: 3,
          requestParams: { page, page_size: 20, query_list: query },
          tableQueryParams: { page, page_size: 20, query_list: query },
        }),
      },
    );
    expect(outcome.kind).toBe('downloaded');
  });

  it('cancels a topology export when the table filter changes', async () => {
    let requestGeneration = 3;
    const runtime = {
      chartType: 'table' as const,
      rawData: { items: [{ host: '上海-1' }], count: 2 },
      loading: false,
      requestGeneration,
      dataSourceId: 7,
      dataSource: {
        params: [
          { name: 'page', type: 'number' },
          { name: 'page_size', type: 'number' },
        ],
      } as never,
      requestParams: {
        page: 1,
        page_size: 20,
        query_list: [{ field: 'host', type: 'str*', value: '上海' }],
      },
      tableQueryParams: {
        page: 1,
        page_size: 20,
        query_list: [{ field: 'host', type: 'str*', value: '上海' }],
      },
      fetchSourceData: async () => {
        requestGeneration = 4;
        return {
          items: [{ host: '上海-1' }],
          count: 2,
          page_size: 1,
        };
      },
    };
    const outcome = await createWidgetCsvExport(
      runtime,
      { title: '主机表' },
      labels,
      CSV_EXPORT_ROW_LIMIT,
      {
        readLatest: () => ({
          ...runtime,
          loading: true,
          requestGeneration,
          requestParams: {
            page: 1,
            page_size: 20,
            query_list: [{ field: 'host', type: 'str*', value: '北京' }],
          },
          tableQueryParams: {
            page: 1,
            page_size: 20,
            query_list: [{ field: 'host', type: 'str*', value: '北京' }],
          },
        }),
      },
    );
    expect(outcome.kind).toBe('stale');
  });

  it('refuses a multi-series radar export', async () => {
    const outcome = await createWidgetCsvExport(
      {
        chartType: 'radar',
        rawData: {
          hostA: [{ name: 'CPU', value: 70 }],
          hostB: [{ name: 'CPU', value: 60 }],
        },
      },
      { title: '雷达' },
      labels,
    );
    expect(outcome.kind).toBe('unsupported');
  });
});
