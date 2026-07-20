# Ops Analysis Param Input Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the early `optionsConfig` implementation with a unified `inputConfig` model that supports input/select/radio, static or dynamic option sources, and `sourceRef/rest_api` defaults for built-in data sources.

**Architecture:** Use one shared data model (`InputControlConfig`) and one shared editor (`paramInputConfigEditor.tsx`) for component parameters and unified filters. Runtime rendering is centralized in `paramInputControl.tsx`, which resolves static options, `sourceId`, or `sourceRef/rest_api`, and falls back to the original input when dynamic options are unavailable.

**Tech Stack:** Next.js 16, React 19, TypeScript, Ant Design, existing `useDataSourceApi`, Django 4.2 NATS handlers, existing OpenSpec change `add-ops-analysis-param-options-source`.

## Global Constraints

- 中文优先：回答、注释、commit、PR、文档一律中文。
- 不在数据源管理参数表提供手动选项配置入口。
- 新模型使用 `inputConfig / InputControlConfig`，不把 `optionsConfig` 作为新主模型。
- `sourceRef` 首版只支持 `{ type: 'rest_api'; value: string }`。
- 动态来源失败、无数据或映射后无选项时回退原始输入控件，不能禁用参数配置。
- 组件配置抽屉和统一筛选共用 `paramInputConfigEditor.tsx` 内部交互。
- 不提供“恢复内置默认”按钮。
- 不做动态来源参数映射、TTL 缓存或数据库迁移。
- 验证 ops-analysis 前端必须使用 `NEXTAPI_INSTALL_APP=ops-analysis pnpm type-check`。
- 文档/spec/plan 不单独提交；提交前必须先征得用户确认。

---

## File Structure

- Create `web/src/app/ops-analysis/utils/paramInputConfigUtils.ts`
  - Owns `normalizeInputConfig`, source ID resolution, response item extraction, and item mapping.
- Create `web/scripts/param-input-config-utils-test.ts`
  - Lightweight tsx tests for pure utility behavior.
- Modify `web/src/app/ops-analysis/types/dataSource.ts`
  - Defines `InputControlConfig`, option source types, `SourceRef`, and `ParamItem.inputConfig`.
- Modify `web/src/app/ops-analysis/types/dashBoard.ts`
  - Adds `UnifiedFilterDefinition.inputConfig`.
- Replace `web/src/app/ops-analysis/components/paramOptionsEditor.tsx` with `web/src/app/ops-analysis/components/paramInputConfigEditor.tsx`
  - Shared editor for input/select/radio and static/dynamic options.
- Replace `web/src/app/ops-analysis/components/paramOptionsSourceSelect.tsx` with `web/src/app/ops-analysis/components/paramInputControl.tsx`
  - Runtime control renderer with dynamic source fallback.
- Modify `web/src/app/ops-analysis/components/paramsConfig.tsx`
  - Renders `ParamInputControl` and exposes edit icon.
- Modify `web/src/app/ops-analysis/components/widgetConfig.tsx`
  - Stores widget-level `inputConfig` overrides.
- Modify `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal.tsx`
  - Uses shared editor and writes `UnifiedFilterDefinition.inputConfig`.
- Modify `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterBar.tsx`
  - Uses shared runtime control for select/radio/input.
- Modify `web/src/app/ops-analysis/(pages)/settings/dataSource/paramTable.tsx`
  - Removes the options column and editor state from the early implementation.
- Modify `web/src/app/ops-analysis/locales/zh.json` and `web/src/app/ops-analysis/locales/en.json`
  - Rename/add `paramInput.*` copy.
- Modify `server/apps/operation_analysis/support-files/source_api.json`
  - Adds `CMDB 机房列表` and `CMDB 3D机房布局.server_room_id.inputConfig`.
- Keep/adjust `server/apps/cmdb/nats/nats.py`, `server/apps/cmdb/services/rack_room.py`, `server/apps/cmdb/tests/test_rack_room_service.py`
  - Ensure CMDB room-list handler and tests match the final sourceRef scenario.

---

### Task 1: Types And Pure Utilities

**Files:**
- Modify: `web/src/app/ops-analysis/types/dataSource.ts`
- Modify: `web/src/app/ops-analysis/types/dashBoard.ts`
- Create: `web/src/app/ops-analysis/utils/paramInputConfigUtils.ts`
- Create: `web/scripts/param-input-config-utils-test.ts`

**Interfaces:**
- Produces:
  - `SourceRef`
  - `InputOption`
  - `InputControlConfig`
  - `normalizeInputConfig(entity): InputControlConfig | undefined`
  - `extractDataSourceItems(response: unknown): Record<string, unknown>[]`
  - `mapDynamicItems(items, valueField, labelField): InputOption[]`
  - `resolveDynamicSourceId(config, dataSources): number | undefined`

- [ ] **Step 1: Write failing utility tests**

Create `web/scripts/param-input-config-utils-test.ts`:

```ts
import assert from 'node:assert/strict';
import {
  extractDataSourceItems,
  mapDynamicItems,
  normalizeInputConfig,
  resolveDynamicSourceId,
} from '../src/app/ops-analysis/utils/paramInputConfigUtils';

const staticOptions = [
  { label: '机房A', value: 1 },
  { label: '机房B', value: '2' },
];

assert.deepEqual(
  normalizeInputConfig({
    inputConfig: { control: 'input' },
  }),
  { control: 'input' },
);

assert.deepEqual(
  normalizeInputConfig({
    options: staticOptions,
  }),
  {
    control: 'select',
    optionsSource: {
      type: 'static',
      staticItems: staticOptions,
    },
  },
);

assert.equal(normalizeInputConfig({}), undefined);

assert.equal(
  resolveDynamicSourceId(
    {
      type: 'dynamic',
      sourceId: 12,
      valueField: '_id',
      labelField: 'inst_name',
    },
    [],
  ),
  12,
);

assert.equal(
  resolveDynamicSourceId(
    {
      type: 'dynamic',
      sourceRef: { type: 'rest_api', value: 'cmdb/get_room_list' },
      valueField: '_id',
      labelField: 'inst_name',
    },
    [
      { id: 8, rest_api: 'monitor/query' },
      { id: 9, rest_api: 'cmdb/get_room_list' },
    ],
  ),
  9,
);

assert.equal(
  resolveDynamicSourceId(
    {
      type: 'dynamic',
      sourceRef: { type: 'rest_api', value: 'cmdb/missing' },
      valueField: '_id',
      labelField: 'inst_name',
    },
    [{ id: 9, rest_api: 'cmdb/get_room_list' }],
  ),
  undefined,
);

assert.deepEqual(extractDataSourceItems({ items: [{ _id: 1 }] }), [{ _id: 1 }]);
assert.deepEqual(extractDataSourceItems({ data: { items: [{ _id: 2 }] } }), [{ _id: 2 }]);
assert.deepEqual(extractDataSourceItems([{ _id: 3 }]), [{ _id: 3 }]);
assert.deepEqual(extractDataSourceItems({ data: null }), []);

assert.deepEqual(
  mapDynamicItems(
    [
      { _id: 1, inst_name: '机房A' },
      { _id: undefined, inst_name: '无ID' },
      { _id: 2, inst_name: null },
    ],
    '_id',
    'inst_name',
  ),
  [
    { value: 1, label: '机房A' },
    { value: 2, label: '' },
  ],
);

console.log('✓ param-input-config-utils-test.ts 全部通过');
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd web && NEXTAPI_INSTALL_APP=ops-analysis pnpm exec tsx scripts/param-input-config-utils-test.ts
```

Expected: fail because `paramInputConfigUtils.ts` does not exist.

- [ ] **Step 3: Add types**

In `web/src/app/ops-analysis/types/dataSource.ts`, add near existing option/param types:

```ts
export interface InputOption {
  label: string;
  value: string | number;
}

export interface RestApiSourceRef {
  type: 'rest_api';
  value: string;
}

export type SourceRef = RestApiSourceRef;

export type StaticOptionsSource = {
  type: 'static';
  staticItems: InputOption[];
};

export type DynamicOptionsSource = {
  type: 'dynamic';
  sourceId?: number;
  sourceRef?: SourceRef;
  valueField: string;
  labelField: string;
};

export type InputControlConfig =
  | {
      control: 'input';
    }
  | {
      control: 'select' | 'radio';
      optionsSource: StaticOptionsSource | DynamicOptionsSource;
    };
```

Extend `ParamItem`:

```ts
inputConfig?: InputControlConfig;
```

Keep existing `options?: ...` for read compatibility, but remove `optionsConfig?: ...` as a target-state field.

In `web/src/app/ops-analysis/types/dashBoard.ts`, import and add:

```ts
import type { InputControlConfig } from './dataSource';

inputConfig?: InputControlConfig;
```

- [ ] **Step 4: Implement utilities**

Create `web/src/app/ops-analysis/utils/paramInputConfigUtils.ts`:

```ts
import type {
  DynamicOptionsSource,
  InputControlConfig,
  InputOption,
} from '@/app/ops-analysis/types/dataSource';

type LegacyOptionsEntity = {
  inputConfig?: InputControlConfig;
  options?: InputOption[];
};

type SourceLike = {
  id: number;
  rest_api?: string;
};

export const normalizeInputConfig = (
  entity?: LegacyOptionsEntity | null,
): InputControlConfig | undefined => {
  if (!entity) return undefined;
  if (entity.inputConfig) return entity.inputConfig;
  if (Array.isArray(entity.options) && entity.options.length > 0) {
    return {
      control: 'select',
      optionsSource: {
        type: 'static',
        staticItems: entity.options,
      },
    };
  }
  return undefined;
};

export const extractDataSourceItems = (
  response: unknown,
): Record<string, unknown>[] => {
  if (Array.isArray(response)) return response as Record<string, unknown>[];
  if (!response || typeof response !== 'object') return [];

  const record = response as Record<string, unknown>;
  if (Array.isArray(record.items)) return record.items as Record<string, unknown>[];

  const data = record.data;
  if (data && typeof data === 'object' && Array.isArray((data as Record<string, unknown>).items)) {
    return (data as Record<string, unknown>).items as Record<string, unknown>[];
  }

  return [];
};

export const mapDynamicItems = (
  items: Record<string, unknown>[],
  valueField: string,
  labelField: string,
): InputOption[] => {
  return items
    .map((item) => {
      const value = item[valueField];
      if (value === undefined || value === null) return null;
      if (typeof value !== 'string' && typeof value !== 'number') return null;
      return {
        value,
        label: String(item[labelField] ?? ''),
      };
    })
    .filter((item): item is InputOption => item !== null);
};

export const resolveDynamicSourceId = (
  source: DynamicOptionsSource,
  dataSources: SourceLike[],
): number | undefined => {
  if (typeof source.sourceId === 'number') return source.sourceId;
  if (source.sourceRef?.type !== 'rest_api') return undefined;
  return dataSources.find((item) => item.rest_api === source.sourceRef?.value)?.id;
};
```

- [ ] **Step 5: Run the utility test**

Run:

```bash
cd web && NEXTAPI_INSTALL_APP=ops-analysis pnpm exec tsx scripts/param-input-config-utils-test.ts
```

Expected:

```txt
✓ param-input-config-utils-test.ts 全部通过
```

---

### Task 2: Shared Editor `paramInputConfigEditor.tsx`

**Files:**
- Create: `web/src/app/ops-analysis/components/paramInputConfigEditor.tsx`
- Modify: `web/src/app/ops-analysis/locales/zh.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`
- Delete later in Task 8: `web/src/app/ops-analysis/components/paramOptionsEditor.tsx`

**Interfaces:**
- Consumes: `InputControlConfig`, `InputOption`, `getDataSourceList`, `getSourceDataByApiId`, `extractDataSourceItems`
- Produces:
  - `ParamInputConfigEditor`
  - Props:

```ts
interface ParamInputConfigEditorProps {
  open: boolean;
  value?: InputControlConfig;
  onConfirm: (value: InputControlConfig) => void;
  onCancel: () => void;
  excludeSourceIds?: number[];
}
```

- [ ] **Step 1: Add i18n keys**

Add these keys to `web/src/app/ops-analysis/locales/zh.json`:

```json
"paramInput": {
  "title": "参数输入配置",
  "controlType": "控件类型",
  "control": {
    "input": "输入框",
    "select": "下拉选择",
    "radio": "单选按钮"
  },
  "sourceType": "选项来源",
  "source": {
    "static": "自定义选项",
    "dynamic": "数据源选项"
  },
  "editButton": "配置输入方式",
  "static": {
    "label": "显示文本",
    "value": "选项值",
    "add": "新增选项",
    "emptyError": "请至少填写一个完整选项",
    "duplicateValueError": "选项值不能重复"
  },
  "dynamic": {
    "sourcePlaceholder": "请选择数据源",
    "valueField": "value",
    "labelField": "label",
    "preview": "预览",
    "refresh": "刷新",
    "loadDataSourceFailed": "数据源列表加载失败",
    "testFailed": "选项源不可用",
    "incomplete": "请选择数据源、value 字段和 label 字段"
  }
}
```

Add equivalent keys to `web/src/app/ops-analysis/locales/en.json`:

```json
"paramInput": {
  "title": "Parameter input settings",
  "controlType": "Control type",
  "control": {
    "input": "Input",
    "select": "Select",
    "radio": "Radio"
  },
  "sourceType": "Option source",
  "source": {
    "static": "Custom options",
    "dynamic": "Data source options"
  },
  "editButton": "Configure input",
  "static": {
    "label": "Label",
    "value": "Value",
    "add": "Add option",
    "emptyError": "Fill in at least one complete option",
    "duplicateValueError": "Option values must be unique"
  },
  "dynamic": {
    "sourcePlaceholder": "Select a data source",
    "valueField": "value",
    "labelField": "label",
    "preview": "Preview",
    "refresh": "Refresh",
    "loadDataSourceFailed": "Failed to load data sources",
    "testFailed": "Option source unavailable",
    "incomplete": "Select a data source, value field, and label field"
  }
}
```

- [ ] **Step 2: Create the editor skeleton**

Create `web/src/app/ops-analysis/components/paramInputConfigEditor.tsx` with this public shape:

```tsx
'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Empty, Input, message, Modal, Radio, Select, Spin, Table } from 'antd';
import { DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import type {
  DatasourceItem,
  DynamicOptionsSource,
  InputControlConfig,
  InputOption,
} from '@/app/ops-analysis/types/dataSource';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { extractDataSourceItems } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import { useTranslation } from '@/utils/i18n';

interface StaticRow extends InputOption {
  uid: string;
}

interface ParamInputConfigEditorProps {
  open: boolean;
  value?: InputControlConfig;
  onConfirm: (value: InputControlConfig) => void;
  onCancel: () => void;
  excludeSourceIds?: number[];
}

const newId = () => Math.random().toString(36).slice(2);
const createRow = (): StaticRow => ({ uid: newId(), label: '', value: '' });

export const ParamInputConfigEditor: React.FC<ParamInputConfigEditorProps> = ({
  open,
  value,
  onConfirm,
  onCancel,
  excludeSourceIds = [],
}) => {
  const { t } = useTranslation();
  const { getDataSourceList, getSourceDataByApiId } = useDataSourceApi();
  const [control, setControl] = useState<InputControlConfig['control']>('input');
  const [sourceType, setSourceType] = useState<'static' | 'dynamic'>('static');
  const [staticRows, setStaticRows] = useState<StaticRow[]>([createRow()]);
  const [dataSourceList, setDataSourceList] = useState<DatasourceItem[]>([]);
  const [dsLoading, setDsLoading] = useState(false);
  const [dynamicSourceId, setDynamicSourceId] = useState<number | undefined>();
  const [dynamicValueField, setDynamicValueField] = useState<string | undefined>();
  const [dynamicLabelField, setDynamicLabelField] = useState<string | undefined>();
  const [dynamicPreview, setDynamicPreview] = useState<Record<string, unknown>[]>([]);
  const [dynamicPreviewLoading, setDynamicPreviewLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (!value) {
      setControl('input');
      setSourceType('static');
      setStaticRows([createRow()]);
      setDynamicSourceId(undefined);
      setDynamicValueField(undefined);
      setDynamicLabelField(undefined);
      setDynamicPreview([]);
      return;
    }

    setControl(value.control);
    if (value.control === 'input') {
      setSourceType('static');
      setStaticRows([createRow()]);
      setDynamicSourceId(undefined);
      setDynamicValueField(undefined);
      setDynamicLabelField(undefined);
      setDynamicPreview([]);
      return;
    }

    if (value.optionsSource.type === 'static') {
      setSourceType('static');
      setStaticRows(
        value.optionsSource.staticItems.length > 0
          ? value.optionsSource.staticItems.map((item) => ({ ...item, uid: newId() }))
          : [createRow()],
      );
      setDynamicSourceId(undefined);
      setDynamicValueField(undefined);
      setDynamicLabelField(undefined);
      setDynamicPreview([]);
      return;
    }

    setSourceType('dynamic');
    setDynamicSourceId(value.optionsSource.sourceId);
    setDynamicValueField(value.optionsSource.valueField);
    setDynamicLabelField(value.optionsSource.labelField);
    setDynamicPreview([]);
  }, [open, value]);

  // The remaining steps fill in data loading, static row editing, preview, and save.
  return <Modal open={open} title={t('paramInput.title')} onCancel={onCancel} footer={null} />;
};
```

- [ ] **Step 3: Fill in datasource loading and preview**

Add inside the component before `return`:

```tsx
  const filteredDataSourceList = useMemo(() => {
    if (excludeSourceIds.length === 0) return dataSourceList;
    return dataSourceList.filter((item) => !excludeSourceIds.includes(item.id));
  }, [dataSourceList, excludeSourceIds]);

  const availableFields = useMemo(() => {
    const first = dynamicPreview[0];
    if (!first) return [];
    return Object.keys(first).map((key) => ({ label: key, value: key }));
  }, [dynamicPreview]);

  useEffect(() => {
    if (!open || sourceType !== 'dynamic' || control === 'input') return;
    setDsLoading(true);
    getDataSourceList({ page_size: -1 })
      .then((response) => {
        const items = Array.isArray(response) ? response : response?.items || [];
        setDataSourceList(items as DatasourceItem[]);
      })
      .catch((error: Error) => {
        message.error(error.message || t('paramInput.dynamic.loadDataSourceFailed'));
      })
      .finally(() => setDsLoading(false));
  }, [control, getDataSourceList, open, sourceType, t]);

  const fetchDynamicPreview = (sourceId: number) => {
    setDynamicPreviewLoading(true);
    getSourceDataByApiId(sourceId, {})
      .then((response) => {
        setDynamicPreview(extractDataSourceItems(response).slice(0, 5));
      })
      .catch((error: any) => {
        setDynamicPreview([]);
        message.error(
          error?.response?.data?.message ||
            error?.message ||
            t('paramInput.dynamic.testFailed'),
        );
      })
      .finally(() => setDynamicPreviewLoading(false));
  };

  useEffect(() => {
    if (!open || control === 'input' || sourceType !== 'dynamic' || !dynamicSourceId) return;
    fetchDynamicPreview(dynamicSourceId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [control, dynamicSourceId, open, sourceType]);
```

- [ ] **Step 4: Fill in save behavior**

Add:

```tsx
  const handleStaticChange = (
    uid: string,
    field: 'label' | 'value',
    nextValue: string,
  ) => {
    setStaticRows((prev) =>
      prev.map((row) =>
        row.uid === uid
          ? {
              ...row,
              [field]:
                field === 'value' && nextValue !== '' && !Number.isNaN(Number(nextValue))
                  ? Number(nextValue)
                  : nextValue,
            }
          : row,
      ),
    );
  };

  const handleAddStaticRow = () => setStaticRows((prev) => [...prev, createRow()]);

  const handleRemoveStaticRow = (uid: string) => {
    setStaticRows((prev) => (prev.length <= 1 ? prev : prev.filter((row) => row.uid !== uid)));
  };

  const handleConfirm = () => {
    if (control === 'input') {
      onConfirm({ control: 'input' });
      return;
    }

    if (sourceType === 'static') {
      const staticItems = staticRows
        .filter((row) => String(row.value).trim() !== '' && row.label.trim() !== '')
        .map(({ label, value }) => ({ label: label.trim(), value }));

      if (staticItems.length === 0) {
        message.warning(t('paramInput.static.emptyError'));
        return;
      }

      const values = new Set(staticItems.map((item) => String(item.value)));
      if (values.size !== staticItems.length) {
        message.warning(t('paramInput.static.duplicateValueError'));
        return;
      }

      onConfirm({
        control,
        optionsSource: {
          type: 'static',
          staticItems,
        },
      });
      return;
    }

    if (!dynamicSourceId || !dynamicValueField || !dynamicLabelField) {
      message.warning(t('paramInput.dynamic.incomplete'));
      return;
    }

    const optionsSource: DynamicOptionsSource = {
      type: 'dynamic',
      sourceId: dynamicSourceId,
      valueField: dynamicValueField,
      labelField: dynamicLabelField,
    };

    onConfirm({ control, optionsSource });
  };
```

- [ ] **Step 5: Replace the Modal render**

Replace the skeleton `return` with:

```tsx
  return (
    <Modal
      title={t('paramInput.title')}
      open={open}
      onCancel={onCancel}
      onOk={handleConfirm}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      width={640}
      centered
      destroyOnHidden
      styles={{
        body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' },
      }}
    >
      <div className="mb-3">
        <div className="mb-2 text-xs text-(--color-text-3)">
          {t('paramInput.controlType')}
        </div>
        <Radio.Group
          value={control}
          onChange={(event) => setControl(event.target.value)}
          optionType="button"
          buttonStyle="solid"
          options={[
            { label: t('paramInput.control.input'), value: 'input' },
            { label: t('paramInput.control.select'), value: 'select' },
            { label: t('paramInput.control.radio'), value: 'radio' },
          ]}
        />
      </div>

      {control !== 'input' && (
        <>
          <div className="mb-3">
            <div className="mb-2 text-xs text-(--color-text-3)">
              {t('paramInput.sourceType')}
            </div>
            <Radio.Group
              value={sourceType}
              onChange={(event) => setSourceType(event.target.value)}
              optionType="button"
              buttonStyle="solid"
              options={[
                { label: t('paramInput.source.static'), value: 'static' },
                { label: t('paramInput.source.dynamic'), value: 'dynamic' },
              ]}
            />
          </div>

          {sourceType === 'static' ? (
            <div className="space-y-2">
              {staticRows.map((row) => (
                <div key={row.uid} className="flex items-center gap-2">
                  <Input
                    value={row.label}
                    placeholder={t('paramInput.static.label')}
                    onChange={(event) => handleStaticChange(row.uid, 'label', event.target.value)}
                  />
                  <Input
                    value={String(row.value)}
                    placeholder={t('paramInput.static.value')}
                    onChange={(event) => handleStaticChange(row.uid, 'value', event.target.value)}
                  />
                  <Button
                    type="text"
                    icon={<DeleteOutlined />}
                    disabled={staticRows.length <= 1}
                    onClick={() => handleRemoveStaticRow(row.uid)}
                  />
                </div>
              ))}
              <Button icon={<PlusOutlined />} onClick={handleAddStaticRow}>
                {t('paramInput.static.add')}
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Select
                  showSearch
                  loading={dsLoading}
                  value={dynamicSourceId}
                  placeholder={t('paramInput.dynamic.sourcePlaceholder')}
                  optionFilterProp="label"
                  style={{ flex: 1 }}
                  options={filteredDataSourceList.map((item) => ({
                    value: item.id,
                    label: `${item.name}（${item.rest_api}）`,
                  }))}
                  onChange={(sourceId) => {
                    setDynamicSourceId(sourceId);
                    setDynamicValueField(undefined);
                    setDynamicLabelField(undefined);
                    fetchDynamicPreview(sourceId);
                  }}
                  notFoundContent={
                    dsLoading ? undefined : (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />
                    )
                  }
                />
                {dynamicSourceId && (
                  <Button
                    type="text"
                    icon={<ReloadOutlined />}
                    title={t('paramInput.dynamic.refresh')}
                    onClick={() => fetchDynamicPreview(dynamicSourceId)}
                  />
                )}
              </div>

              {dynamicPreviewLoading ? (
                <div className="py-6 text-center">
                  <Spin size="small" />
                </div>
              ) : (
                <>
                  <Select
                    value={dynamicValueField}
                    placeholder={t('paramInput.dynamic.valueField')}
                    style={{ width: '100%' }}
                    options={availableFields}
                    onChange={setDynamicValueField}
                  />
                  <Select
                    value={dynamicLabelField}
                    placeholder={t('paramInput.dynamic.labelField')}
                    style={{ width: '100%' }}
                    options={availableFields}
                    onChange={setDynamicLabelField}
                  />
                  <Table
                    size="small"
                    pagination={false}
                    dataSource={dynamicPreview}
                    rowKey={(_, index) => String(index)}
                    columns={[
                      {
                        title: t('paramInput.dynamic.preview'),
                        dataIndex: dynamicLabelField || '',
                        render: (text) => String(text ?? ''),
                      },
                    ]}
                  />
                </>
              )}
            </div>
          )}
        </>
      )}
    </Modal>
  );
```

- [ ] **Step 6: Type-check just this area through app type-check**

Run:

```bash
cd web && NEXTAPI_INSTALL_APP=ops-analysis pnpm type-check
```

Expected: either pass or fail only on downstream files not yet updated to import the new component. If it fails on missing imports from later tasks, proceed to Task 3.

---

### Task 3: Runtime Control `paramInputControl.tsx`

**Files:**
- Create: `web/src/app/ops-analysis/components/paramInputControl.tsx`
- Delete later in Task 8: `web/src/app/ops-analysis/components/paramOptionsSourceSelect.tsx`

**Interfaces:**
- Consumes: `InputControlConfig`, `ParamItem`, `DatasourceItem[]`
- Produces:

```ts
interface ParamInputControlProps {
  inputConfig?: InputControlConfig;
  fallback: React.ReactNode;
  value?: string | number;
  onChange?: (value: string | number | null) => void;
  disabled?: boolean;
  placeholder?: string;
  allowClear?: boolean;
  style?: React.CSSProperties;
}
```

- [ ] **Step 1: Create the runtime component**

Create `web/src/app/ops-analysis/components/paramInputControl.tsx`:

```tsx
'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Radio, Select, Spin } from 'antd';
import type { InputControlConfig, InputOption } from '@/app/ops-analysis/types/dataSource';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import {
  extractDataSourceItems,
  mapDynamicItems,
  resolveDynamicSourceId,
} from '@/app/ops-analysis/utils/paramInputConfigUtils';

interface ParamInputControlProps {
  inputConfig?: InputControlConfig;
  fallback: React.ReactNode;
  value?: string | number;
  onChange?: (value: string | number | null) => void;
  disabled?: boolean;
  placeholder?: string;
  allowClear?: boolean;
  style?: React.CSSProperties;
}

type FetchState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; options: InputOption[] }
  | { status: 'error' };

export const ParamInputControl: React.FC<ParamInputControlProps> = ({
  inputConfig,
  fallback,
  value,
  onChange,
  disabled,
  placeholder,
  allowClear = true,
  style,
}) => {
  const { getDataSourceList, getSourceDataByApiId } = useDataSourceApi();
  const requestIdRef = useRef(0);
  const [state, setState] = useState<FetchState>({ status: 'idle' });

  const staticOptions = useMemo(() => {
    if (!inputConfig || inputConfig.control === 'input') return undefined;
    if (inputConfig.optionsSource.type !== 'static') return undefined;
    return inputConfig.optionsSource.staticItems;
  }, [inputConfig]);

  useEffect(() => {
    if (!inputConfig || inputConfig.control === 'input') return;
    if (inputConfig.optionsSource.type === 'static') {
      setState({ status: 'success', options: inputConfig.optionsSource.staticItems });
      return;
    }

    const source = inputConfig.optionsSource;
    const requestId = ++requestIdRef.current;
    setState({ status: 'loading' });

    const load = async () => {
      try {
        const dataSources = source.sourceRef
          ? await getDataSourceList({ page_size: -1 })
          : [];
        const sourceItems = Array.isArray(dataSources)
          ? dataSources
          : dataSources?.items || [];
        const sourceId = resolveDynamicSourceId(source, sourceItems);
        if (!sourceId) {
          if (requestId === requestIdRef.current) setState({ status: 'error' });
          return;
        }
        const response = await getSourceDataByApiId(sourceId, {});
        const options = mapDynamicItems(
          extractDataSourceItems(response),
          source.valueField,
          source.labelField,
        );
        if (requestId === requestIdRef.current) {
          setState(options.length > 0 ? { status: 'success', options } : { status: 'error' });
        }
      } catch {
        if (requestId === requestIdRef.current) setState({ status: 'error' });
      }
    };

    load();
  }, [getDataSourceList, getSourceDataByApiId, inputConfig]);

  if (!inputConfig || inputConfig.control === 'input') return <>{fallback}</>;
  if (state.status === 'loading') return <Spin size="small" />;
  if (state.status !== 'success' || state.options.length === 0) return <>{fallback}</>;

  if (inputConfig.control === 'radio') {
    return (
      <Radio.Group
        value={value}
        disabled={disabled}
        options={state.options}
        optionType="button"
        buttonStyle="outline"
        onChange={(event) => onChange?.(event.target.value ?? null)}
      />
    );
  }

  return (
    <Select
      value={value}
      disabled={disabled}
      placeholder={placeholder}
      allowClear={allowClear}
      style={{ width: '100%', ...style }}
      options={staticOptions || state.options}
      onChange={(nextValue) => onChange?.(nextValue ?? null)}
    />
  );
};
```

- [ ] **Step 2: Run type-check**

Run:

```bash
cd web && NEXTAPI_INSTALL_APP=ops-analysis pnpm type-check
```

Expected: fail only where old imports still reference `ParamOptionsSourceSelect` or old fields. Those are fixed in Tasks 4-6.

---

### Task 4: Component Parameter Rendering And Widget Overrides

**Files:**
- Modify: `web/src/app/ops-analysis/components/paramsConfig.tsx`
- Modify: `web/src/app/ops-analysis/components/widgetConfig.tsx`

**Interfaces:**
- Consumes: `ParamInputControl`, `ParamInputConfigEditor`, `normalizeInputConfig`
- Produces: widget-level `valueConfig.dataSourceParams[i].inputConfig`

- [ ] **Step 1: Update `DataSourceParamsConfig` props**

In `paramsConfig.tsx`, replace old `onEditOptions` with:

```ts
onEditInputConfig?: (param: ParamItem) => void;
```

- [ ] **Step 2: Wrap existing fallback inputs**

Inside `renderParamInput(param)`, keep the existing switch for date/time/number/string as a helper:

```tsx
const renderFallbackInput = () => {
  switch (type) {
    case 'timeRange':
      return <FormTimeSelector disabled={isDisabled} />;
    case 'date':
      return <DatePicker showTime placeholder={t('common.selectTip')} style={{ width: '100%' }} disabled={isDisabled} />;
    case 'number':
      return <InputNumber placeholder={t('common.inputTip')} style={{ width: '100%' }} disabled={isDisabled} />;
    default:
      return <Input placeholder={t('common.inputTip')} disabled={isDisabled} />;
  }
};
```

Then render:

```tsx
const inputConfig = normalizeInputConfig(param);

return (
  <ParamInputControl
    inputConfig={inputConfig}
    fallback={renderFallbackInput()}
    disabled={isDisabled}
    placeholder={t('common.selectTip')}
  />
);
```

- [ ] **Step 3: Rename edit button callback**

Where the config icon is rendered, call:

```tsx
onEditInputConfig?.(param)
```

and use tooltip:

```tsx
t('paramInput.editButton')
```

- [ ] **Step 4: Update widget override state**

In `widgetConfig.tsx`, rename state and handlers:

```ts
const [editingInputParam, setEditingInputParam] = useState<ParamItem | null>(null);
const [widgetParamOverrides, setWidgetParamOverrides] = useState<ParamItem[]>([]);

const handleEditInputConfig = (param: ParamItem) => {
  const override = widgetParamOverrides.find((item) => item.name === param.name);
  setEditingInputParam(override ?? param);
};

const handleInputConfigConfirm = (inputConfig: InputControlConfig) => {
  if (!editingInputParam) return;
  setWidgetParamOverrides((prev) => {
    const baseParam = {
      ...editingInputParam,
      inputConfig,
      options: undefined,
    };
    const exists = prev.some((item) => item.name === editingInputParam.name);
    return exists
      ? prev.map((item) => (item.name === editingInputParam.name ? baseParam : item))
      : [...prev, baseParam];
  });
  setEditingInputParam(null);
};
```

- [ ] **Step 5: Merge widget overrides into selected data source**

Replace old `optionsConfig` merge:

```ts
const effectiveDataSource = useMemo(() => {
  if (!selectedDataSource) return undefined;
  if (widgetParamOverrides.length === 0) return selectedDataSource;
  return {
    ...selectedDataSource,
    params: selectedDataSource.params.map((param) => {
      const override = widgetParamOverrides.find((item) => item.name === param.name);
      return override?.inputConfig ? { ...param, inputConfig: override.inputConfig } : param;
    }),
  };
}, [selectedDataSource, widgetParamOverrides]);
```

- [ ] **Step 6: Restore overrides from saved widget config**

In the drawer initialization path, replace old `optionsConfig` filtering with:

```ts
const savedInputOverrides = (valueConfig.dataSourceParams || []).filter(
  (param: ParamItem) => param.inputConfig,
);
setWidgetParamOverrides(savedInputOverrides);
```

- [ ] **Step 7: Render the editor**

Replace old editor render:

```tsx
<ParamInputConfigEditor
  key={editingInputParam?.name ?? 'closed'}
  open={editingInputParam !== null}
  value={normalizeInputConfig(editingInputParam)}
  onConfirm={handleInputConfigConfirm}
  onCancel={() => setEditingInputParam(null)}
  excludeSourceIds={selectedDataSource ? [selectedDataSource.id] : []}
/>
```

- [ ] **Step 8: Run type-check**

Run:

```bash
cd web && NEXTAPI_INSTALL_APP=ops-analysis pnpm type-check
```

Expected: remaining failures, if any, are in unified filter or old deleted component references.

---

### Task 5: Unified Filter Editor And Runtime

**Files:**
- Modify: `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal.tsx`
- Modify: `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterBar.tsx`
- Delete: `web/src/app/ops-analysis/components/unifiedFilter/filterOptionsModal.tsx`

**Interfaces:**
- Consumes: `ParamInputConfigEditor`, `ParamInputControl`, `normalizeInputConfig`
- Produces: `UnifiedFilterDefinition.inputConfig`

- [ ] **Step 1: Update unified filter type usage**

Where a filter definition is converted for editing, use:

```ts
const getEditingFilterInputConfig = () => {
  const definition = definitions.find((item) => item.id === editingFilterId);
  return normalizeInputConfig(definition);
};
```

- [ ] **Step 2: Replace options confirm handler**

Use:

```ts
const handleInputConfigConfirm = (inputConfig: InputControlConfig) => {
  if (!editingFilterId) return;
  setDefinitions((prev) =>
    prev.map((definition) =>
      definition.id === editingFilterId
        ? sanitizeUnifiedFilterDefinition({
            ...definition,
            inputConfig,
            inputMode: inputConfig.control,
            options: undefined,
          })
        : definition,
    ),
  );
  setEditingFilterId(null);
  setInputConfigModalOpen(false);
};
```

- [ ] **Step 3: Render shared editor**

Replace old `FilterOptionsModal`/`ParamOptionsEditor` with:

```tsx
<ParamInputConfigEditor
  key={editingFilterId ?? 'closed'}
  open={inputConfigModalOpen}
  value={getEditingFilterInputConfig()}
  onConfirm={handleInputConfigConfirm}
  onCancel={() => {
    setEditingFilterId(null);
    setInputConfigModalOpen(false);
  }}
/>
```

- [ ] **Step 4: Update unified filter bar runtime**

In `unifiedFilterBar.tsx`, build fallback per existing type logic, then wrap:

```tsx
const inputConfig = normalizeInputConfig(definition);

return (
  <ParamInputControl
    inputConfig={inputConfig}
    fallback={fallbackNode}
    value={(typeof value === 'string' || typeof value === 'number') ? value : undefined}
    onChange={(nextValue) => handleLocalValueChange(definition.id, nextValue ?? null)}
    placeholder={definition.name}
    style={{ minWidth: 160 }}
  />
);
```

Ensure `radio` does not use `definition.options` directly.

- [ ] **Step 5: Delete old modal file**

Delete:

```txt
web/src/app/ops-analysis/components/unifiedFilter/filterOptionsModal.tsx
```

- [ ] **Step 6: Run type-check**

Run:

```bash
cd web && NEXTAPI_INSTALL_APP=ops-analysis pnpm type-check
```

Expected: failures should now be only old `paramOptions*` references or source API data until Tasks 6-8.

---

### Task 6: Data Source Table Cleanup And Built-in JSON

**Files:**
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/paramTable.tsx`
- Modify: `server/apps/operation_analysis/support-files/source_api.json`

**Interfaces:**
- Produces: no data-source-management edit entry for input config.
- Produces: built-in `inputConfig` on `CMDB 3D机房布局.server_room_id`.

- [ ] **Step 1: Remove ParamTable options UI**

In `paramTable.tsx`, remove:

```ts
editingOptionsParam
handleOptionsConfirm
normalizeOptionsConfig import
ParamOptionsEditor import
SettingOutlined import if it becomes unused
```

Remove the column with:

```ts
title: t("dataSource.options")
```

Remove the editor render block:

```tsx
<ParamOptionsEditor ... />
```

- [ ] **Step 2: Confirm only foundational parameter fields remain**

The columns should remain focused on:

```txt
name / alias_name / type / filterType / value / operation
```

- [ ] **Step 3: Update `source_api.json` for CMDB room defaults**

For `CMDB 3D机房布局`, set `server_room_id` param to include:

```json
"inputConfig": {
  "control": "select",
  "optionsSource": {
    "type": "dynamic",
    "sourceRef": {
      "type": "rest_api",
      "value": "cmdb/get_room_list"
    },
    "valueField": "_id",
    "labelField": "inst_name"
  }
}
```

Ensure `CMDB 机房列表` exists:

```json
{
  "name": "CMDB 机房列表",
  "desc": "返回 CMDB 中所有 server_room 列表（按当前用户权限过滤），保留原始字段 _id/inst_name 等。供运维分析参数动态选项源使用；本身不直接出图。",
  "rest_api": "cmdb/get_room_list",
  "tag": ["cmdb"],
  "chart_type": [],
  "field_schema": [],
  "params": []
}
```

- [ ] **Step 4: Validate JSON**

Run:

```bash
python -m json.tool server/apps/operation_analysis/support-files/source_api.json >/tmp/source_api.json
```

Expected: command exits 0.

---

### Task 7: CMDB Room List Backend Alignment

**Files:**
- Modify: `server/apps/cmdb/services/rack_room.py`
- Modify: `server/apps/cmdb/nats/nats.py`
- Modify: `server/apps/cmdb/tests/test_rack_room_service.py`

**Interfaces:**
- Produces:
  - `list_server_rooms(permission_map: dict | None = None, user_info=None) -> list`
  - NATS handler `get_room_list(user_info=None, **kwargs) -> {"items": list}`

- [ ] **Step 1: Ensure service function matches final contract**

In `rack_room.py`, keep implementation equivalent to:

```py
_ROOM_LIST_PAGE_SIZE = 1000


def list_server_rooms(permission_map: dict | None = None, user_info=None) -> list:
    """列出当前用户可见的 server_room，返回 CMDB 原始字段。"""
    inst_list, _count = InstanceManage.instance_list(
        model_id="server_room",
        params=[],
        page=1,
        page_size=_ROOM_LIST_PAGE_SIZE,
        order="inst_name",
        permission_map=permission_map or {},
    )
    return inst_list or []
```

- [ ] **Step 2: Ensure NATS handler matches final contract**

In `nats.py`, keep implementation equivalent to:

```py
@nats_client.register
def get_room_list(user_info=None, **kwargs):
    """获取运营分析参数动态选项源用的机房列表。"""
    permission_map = _build_nats_permission_map(user_info) or {}
    items = rack_room.list_server_rooms(permission_map=permission_map, user_info=user_info)
    return {"items": items}
```

- [ ] **Step 3: Ensure tests cover contract**

In `test_rack_room_service.py`, ensure tests assert:

```py
assert kwargs["model_id"] == "server_room"
assert kwargs["permission_map"] == perm
assert kwargs["page"] == 1
assert kwargs["page_size"] == 1000
assert kwargs["order"] == "inst_name"
assert result == [{"_id": 1, "inst_name": "机房A", "model_id": "server_room"}]
assert nats.get_room_list(user_info={"user": "alice"}) == {
    "items": [{"_id": 1, "inst_name": "机房A", "model_id": "server_room"}]
}
```

- [ ] **Step 4: Run targeted backend tests**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/test_rack_room_service.py -q
```

Expected: tests in `TestListServerRooms` and `TestGetRoomListNatsHandler` pass. If unrelated collection errors appear, capture the exact error and run the narrowest available pytest target.

---

### Task 8: Rename/Cleanup Old Param Options Implementation

**Files:**
- Delete: `web/src/app/ops-analysis/components/paramOptionsEditor.tsx`
- Delete: `web/src/app/ops-analysis/components/paramOptionsSourceSelect.tsx`
- Delete: `web/src/app/ops-analysis/utils/paramOptionsUtils.ts`
- Delete or replace: `web/scripts/param-options-source-utils-test.ts`
- Modify: imports across `web/src/app/ops-analysis`

**Interfaces:**
- Produces: no runtime references to `ParamOptions*`, `paramOptions.*`, or `optionsConfig` as new model.

- [ ] **Step 1: Search old names**

Run:

```bash
rg -n "ParamOptions|paramOptions|paramOptionsUtils|ParamOptionsSourceSelect|optionsConfig" web/src/app/ops-analysis web/scripts
```

Expected: shows remaining old references to remove or compatibility mentions to evaluate.

- [ ] **Step 2: Remove old files**

Delete:

```txt
web/src/app/ops-analysis/components/paramOptionsEditor.tsx
web/src/app/ops-analysis/components/paramOptionsSourceSelect.tsx
web/src/app/ops-analysis/utils/paramOptionsUtils.ts
web/scripts/param-options-source-utils-test.ts
```

- [ ] **Step 3: Replace imports**

Replace old imports with:

```ts
import { ParamInputConfigEditor } from '@/app/ops-analysis/components/paramInputConfigEditor';
import { ParamInputControl } from '@/app/ops-analysis/components/paramInputControl';
import { normalizeInputConfig } from '@/app/ops-analysis/utils/paramInputConfigUtils';
```

- [ ] **Step 4: Confirm old model is not used**

Run:

```bash
rg -n "optionsConfig|ParamOptions|paramOptions" web/src/app/ops-analysis web/scripts
```

Expected: no matches, except intentional comments in migration notes if they remain in OpenSpec/docs.

---

### Task 9: Final Verification

**Files:**
- All touched files.

**Interfaces:**
- Consumes all previous tasks.
- Produces verified working branch state.

- [ ] **Step 1: Run utility test**

Run:

```bash
cd web && NEXTAPI_INSTALL_APP=ops-analysis pnpm exec tsx scripts/param-input-config-utils-test.ts
```

Expected:

```txt
✓ param-input-config-utils-test.ts 全部通过
```

- [ ] **Step 2: Run type-check**

Run:

```bash
cd web && NEXTAPI_INSTALL_APP=ops-analysis pnpm type-check
```

Expected: exits 0.

- [ ] **Step 3: Run CMDB backend tests**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/test_rack_room_service.py -q
```

Expected: targeted tests pass. If repository-level collection is blocked by known unrelated dependencies, record the exact blocker in the final report.

- [ ] **Step 4: Validate OpenSpec**

Run:

```bash
openspec validate add-ops-analysis-param-options-source --strict
```

Expected:

```txt
Change 'add-ops-analysis-param-options-source' is valid
```

- [ ] **Step 5: Check formatting whitespace**

Run:

```bash
git diff --check
```

Expected: no whitespace errors. Current unrelated CMDB blank-line-at-EOF warnings must be fixed if they remain in touched files.

- [ ] **Step 6: Manual verification checklist**

Verify in the UI:

```txt
1. 组件配置选择 CMDB 3D机房布局后，server_room_id 默认显示机房下拉。
2. 动态来源失败时，server_room_id 回退为普通输入，配置 icon 仍可打开。
3. 组件参数编辑器和统一筛选编辑器内部都是：输入框 / 下拉选择 / 单选按钮，再选择自定义选项 / 数据源选项。
4. 统一筛选 select 和 radio 都能使用动态来源。
5. 数据源管理参数表没有“选项”列。
```

- [ ] **Step 7: Prepare final change summary**

Summarize:

```txt
1. inputConfig model and sourceRef/rest_api support.
2. Shared editor/runtime for component params and unified filters.
3. Data source param table option entry removed.
4. CMDB room list default source wired.
5. Verification commands and results.
```

Do not commit unless the user explicitly confirms.
