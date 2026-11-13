import { describe, expect, it } from 'vitest';

import {
  columnsFromModelFields,
  formatModelCell,
  modelCellDisplayText,
  modelTableEmptyText,
  reconcileSavedModelColumns,
  resolveModelAttrColumns,
  schemaFieldsForTable,
} from '@/app/ops-analysis/utils/modelTableColumns';
import { resolveTableLikeColumns } from '@/app/ops-analysis/utils/tableLikeData';
import { buildTableCsvTable } from '@/app/ops-analysis/utils/widgetCsvExport';

const simulatedFields = [
  {
    key: 'inst_name',
    title: '实例名称',
    attr_type: 'str',
    default_visible: true,
  },
  {
    key: 'cpu',
    title: 'CPU',
    attr_type: 'int',
    default_visible: true,
  },
  {
    key: 'enabled',
    title: '是否启用',
    attr_type: 'bool',
    default_visible: true,
  },
  {
    key: 'status',
    title: '运行状态',
    attr_type: 'enum',
    default_visible: true,
    display_key: 'status_display',
    options: [
      { value: '1', label: '运行中' },
      { value: '0', label: '停止' },
    ],
  },
  {
    key: 'organization',
    title: '组织',
    attr_type: 'organization',
    default_visible: true,
    display_key: 'organization_display',
  },
  {
    key: 'owner',
    title: '负责人',
    attr_type: 'user',
    default_visible: true,
    display_key: 'owner_display',
  },
  {
    key: 'created_at',
    title: '创建时间',
    attr_type: 'time',
    default_visible: true,
    display_format: 'datetime',
  },
  {
    key: 'extra',
    title: '扩展',
    attr_type: 'table',
    default_visible: true,
  },
  {
    key: 'inst_uuid',
    title: '实例标识',
    attr_type: 'str',
    default_visible: false,
  },
];

describe('model attribute columns', () => {
  it('formats 0, false, enum, display fallback, time and objects without inventing text', () => {
    const row = {
      cpu: 0,
      enabled: false,
      status: '1',
      status_display: '运行中',
      organization: [7],
      organization_display: '研发',
      owner: 'user-9',
      created_at: '2026-11-11T01:02:03Z',
      extra: { port: 80 },
      missing_enum: 0,
    };
    const byKey = Object.fromEntries(simulatedFields.map((field) => [field.key, field]));

    expect(formatModelCell(row.cpu, { attrType: byKey.cpu.attr_type }, row)).toBe('0');
    expect(formatModelCell(row.enabled, { attrType: 'bool' }, row)).toBe('NO');
    expect(formatModelCell(true, { attrType: 'bool' })).toBe('YES');
    expect(formatModelCell(row.status, {
      attrType: 'enum',
      displayKey: 'status_display',
      options: byKey.status.options,
    }, row)).toBe('运行中');
    expect(formatModelCell(0, {
      attrType: 'enum',
      options: byKey.status.options,
    })).toBe('停止');
    expect(formatModelCell('9', {
      attrType: 'enum',
      displayKey: 'status_display',
      options: byKey.status.options,
    }, { status_display: '' })).toBe('9');
    expect(formatModelCell(row.organization, {
      attrType: 'organization',
      displayKey: 'organization_display',
    }, row)).toBe('研发');
    expect(formatModelCell([8], { attrType: 'organization', displayKey: 'organization_display' }, {})).toBe('8');
    expect(formatModelCell(row.owner, { attrType: 'user', displayKey: 'owner_display' }, row)).toBe('user-9');
    expect(formatModelCell(row.created_at, { attrType: 'time', displayFormat: 'datetime' })).toContain('2026-11-11');
    expect(formatModelCell('not-a-time', { attrType: 'time' })).toBe('not-a-time');
    expect(formatModelCell(row.extra, { attrType: 'table' })).toBe('{"port":80}');
    expect(formatModelCell(null, { attrType: 'str' })).toBe('--');
    expect(formatModelCell('', { attrType: 'int' })).toBe('--');
  });

  it('keeps a user mapping ahead of model formatting', () => {
    const column = {
      ...columnsFromModelFields(simulatedFields)[3],
      valueMappings: [{ type: 'value' as const, value: '1', result: { text: '自定义' } }],
    };
    expect(modelCellDisplayText('1', column, { status_display: '运行中' })).toBeNull();
  });

  it('drops a saved column when the model key changes and refreshes the same model title', () => {
    const catalog = columnsFromModelFields(simulatedFields);
    const saved = [{
      key: 'status',
      title: '旧模型的状态',
      visible: false,
      order: 0,
      modelFormat: { attrType: 'str' },
    }];
    const mismatched = resolveModelAttrColumns({
      configuredColumns: saved,
      columnModelKey: 'app',
      modelColumns: { source: 'model_attrs', model_key: 'host', fields: simulatedFields },
    });
    expect(mismatched.find((column) => column.key === 'status')?.title).toBe('运行状态');
    expect(mismatched.find((column) => column.key === 'status')?.visible).toBe(true);

    const sameModel = reconcileSavedModelColumns(saved, catalog);
    expect(sameModel).toHaveLength(1);
    expect(sameModel[0].title).toBe('运行状态');
    expect(sameModel[0].visible).toBe(false);
    expect(sameModel[0].modelFormat?.attrType).toBe('enum');
  });

  it('lets old sources ignore table:false only when the flag is present', () => {
    const rows = [{ name: '甲', value: 1, status: 'active' }];
    const schema = [
      { key: 'name', title: '名称' },
      { key: 'value', title: '值', table: false },
      { key: 'status', title: '状态' },
    ];
    expect(schemaFieldsForTable(schema).map((field) => field.key)).toEqual(['name', 'status']);
    expect(resolveTableLikeColumns({ schemaFields: schema, rows }).map((column) => column.key)).toEqual([
      'name',
      'status',
    ]);
    expect(resolveTableLikeColumns({
      schemaFields: schema.map((field) => ({ key: field.key, title: field.title })),
      rows,
    }).map((column) => column.key)).toEqual(['name', 'value', 'status']);
    expect(resolveTableLikeColumns({
      configuredColumns: [{ key: 'name', title: '旧标题', visible: true, order: 0 }],
      columnModelKey: 'other',
      modelColumns: { source: 'model_attrs', model_key: 'host', fields: simulatedFields },
      schemaFields: schema,
      rows,
    }).find((column) => column.key === 'inst_name')?.title).toBe('实例名称');
  });

  it('hides the other query object columns when a table already saved them', () => {
    const schema = [
      { key: 'alert_id', title: '告警标识', query_objects: ['alert'] },
      { key: 'event_id', title: '事件标识', query_objects: ['event'] },
      { key: 'title', title: '标题' },
    ];
    const configuredColumns = [
      { key: 'alert_id', title: '告警标识', visible: true, order: 0 },
      { key: 'event_id', title: '事件标识', visible: true, order: 1 },
      { key: 'title', title: '标题', visible: true, order: 2 },
    ];
    expect(resolveTableLikeColumns({
      configuredColumns,
      schemaFields: schema,
      queryObject: 'alert',
      rows: [{ alert_id: 'A-1', title: '磁盘' }],
    }).map((column) => column.key)).toEqual(['alert_id', 'title']);
    expect(resolveTableLikeColumns({
      schemaFields: schema,
      queryObject: 'event',
      rows: [],
    }).map((column) => column.key)).toEqual(['event_id', 'title']);
  });

  it('asks for a model or relation before querying and exports formatted cells', () => {
    const t = (key: string) => key;
    expect(modelTableEmptyText('cmdb/query_cmdb_instances', {}, t)).toBe('dashboard.selectModel');
    expect(modelTableEmptyText('cmdb/query_cmdb_instances', { model_id: 'host' }, t)).toBeNull();
    expect(modelTableEmptyText('cmdb/query_cmdb_one_hop', { start_model_id: 'host' }, t)).toBe(
      'dashboard.selectModelRelationFirst',
    );
    expect(modelTableEmptyText('monitor/query_monitor_alerts', {}, t)).toBeNull();

    const rawData = {
      items: [{ status: '1', status_display: '运行中', cpu: 0, enabled: false }],
      column_fields: { source: 'model_attrs', model_key: 'host', fields: simulatedFields },
    };
    const table = buildTableCsvTable('table', rawData.items, {
      tableConfig: { columnModelKey: 'host', columns: [] },
    }, undefined, rawData);
    expect(table.headers[0]).toBe('实例名称');
    expect(table.headers).toContain('运行状态');
    expect(table.headers).not.toContain('实例标识');
    const statusIndex = table.headers.indexOf('运行状态');
    const cpuIndex = table.headers.indexOf('CPU');
    const enabledIndex = table.headers.indexOf('是否启用');
    expect(table.rows[0][statusIndex]).toBe('运行中');
    expect(table.rows[0][cpuIndex]).toBe('0');
    expect(table.rows[0][enabledIndex]).toBe('NO');
  });
});
