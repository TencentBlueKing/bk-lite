'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, DatePicker, Drawer, Input, InputNumber, Modal, Select, Tag, message } from 'antd';
import GroupTreeSelector from '@/components/group-tree-select';
import dayjs from 'dayjs';
import { useModelApi } from '@/app/cmdb/api';
import { useSavedFiltersApi, type AdvancedFilterValue, type SavedFiltersConfigValue } from '@/app/cmdb/api/userConfig';
import { useAssetDataStore } from '@/app/cmdb/store';
import type { AssoTypeItem, AttrFieldType, ModelItem, UserItem } from '@/app/cmdb/types/assetManage';
import { useTranslation } from '@/utils/i18n';
import { isSearchableFilterAttr } from '../searchFilterAttrs';
import {
  buildPathChoices,
  conditionValueText,
  operatorNeedsValue,
  operatorsFor,
  otherModelId,
  summarizeCondition,
  type AdvancedCondition,
  type AdvancedLogic,
  type AssocEdge,
  type PathChoice,
} from './advancedFilter';

const SAVED_FILTERS_CONFIG_KEY = 'cmdb_saved_filters';

interface DraftCondition extends AdvancedCondition {
  key: string;
}

interface AdvancedFilterDrawerProps {
  open: boolean;
  modelId: string;
  applied: AdvancedFilterValue | null;
  attrList: AttrFieldType[];
  userList: UserItem[];
  assoTypes: AssoTypeItem[];
  models: ModelItem[];
  onClose: () => void;
  onApply: (filter: AdvancedFilterValue | null) => void;
}

function newKey() {
  return `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function toDrafts(filter: AdvancedFilterValue | null): DraftCondition[] {
  return (filter?.conditions || []).map((item) => ({ ...item, key: newKey() }));
}

function optionItems(option: AttrFieldType['option']) {
  if (!Array.isArray(option)) return [];
  return option.map((item) => {
    if (typeof item === 'string' || typeof item === 'number') {
      return { label: String(item), value: String(item) };
    }
    const record = item as { id?: string; name?: string; value?: string; label?: string };
    const value = String(record.id ?? record.value ?? '');
    return { label: String(record.name ?? record.label ?? value), value };
  }).filter((item) => item.value);
}

function searchableAttrs(attrs: AttrFieldType[]) {
  return attrs.filter((attr) => isSearchableFilterAttr(attr.attr_type) && !attr.is_display_field);
}

export function AdvancedFilterChips({
  modelId,
  filter,
  attrList,
  assoTypes,
  models,
  onChange,
}: {
  modelId: string;
  filter: AdvancedFilterValue | null;
  attrList: AttrFieldType[];
  assoTypes: AssoTypeItem[];
  models: ModelItem[];
  onChange: (filter: AdvancedFilterValue | null) => void;
}) {
  const { t } = useTranslation();
  const { getModelAttrList } = useModelApi();
  const edges = useModelEdges(modelId, Boolean(filter?.conditions?.length));
  const [relatedAttrs, setRelatedAttrs] = useState<Record<string, AttrFieldType[]>>({});
  const choices = useMemo(
    () => buildPathChoices(modelId, edges, relationName(assoTypes), modelName(models)),
    [modelId, edges, assoTypes, models],
  );
  useEffect(() => {
    const missing = [...new Set((filter?.conditions || []).map((condition) => {
      const choice = choices.find((item) => JSON.stringify(item.path) === JSON.stringify(condition.path));
      return choice?.endModelId;
    }).filter((id): id is string => Boolean(id && id !== modelId && !relatedAttrs[id])))];
    missing.forEach((id) => {
      getModelAttrList(id).then((attrs: AttrFieldType[]) => {
        setRelatedAttrs((current) => ({ ...current, [id]: attrs || [] }));
      }).catch(() => setRelatedAttrs((current) => ({ ...current, [id]: [] })));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter, choices, modelId, relatedAttrs]);

  if (!filter?.conditions?.length) return null;

  const remove = (index: number) => {
    const conditions = filter.conditions.filter((_, itemIndex) => itemIndex !== index);
    onChange(conditions.length ? { ...filter, conditions } : null);
  };

  return (
    <div className="mb-2 flex flex-wrap items-center gap-2">
      {filter.conditions.map((condition, index) => {
        const choice = choices.find((item) => JSON.stringify(item.path) === JSON.stringify(condition.path));
        const endModelId = choice?.endModelId;
        const field = (endModelId && endModelId !== modelId ? relatedAttrs[endModelId] : attrList)
          ?.find((attr) => attr.attr_id === condition.field);
        const operator = operatorsFor(field?.attr_type || 'str').find((item) => item.value === condition.type);
        const text = summarizeCondition(
          choice?.label || t('AdvancedFilter.currentModel'),
          field?.attr_name || condition.field,
          operator?.label || condition.type,
          conditionValueText(condition),
        );
        return (
          <Tag key={`${condition.field}-${index}`} closable onClose={() => remove(index)}>
            {text}
          </Tag>
        );
      })}
      <Button type="link" size="small" onClick={() => onChange(null)}>
        {t('AdvancedFilter.clearAll')}
      </Button>
    </div>
  );
}

export default function AdvancedFilterDrawer({
  open,
  modelId,
  applied,
  attrList,
  userList,
  assoTypes,
  models,
  onClose,
  onApply,
}: AdvancedFilterDrawerProps) {
  const { t } = useTranslation();
  const { getModelAttrList } = useModelApi();
  const { saveFilters } = useSavedFiltersApi();
  const userConfigs = useAssetDataStore((state) => state.user_configs);
  const updateUserConfig = useAssetDataStore((state) => state.updateUserConfig);
  const queryList = useAssetDataStore((state) => state.query_list);
  const edges = useModelEdges(modelId, open);
  const [logic, setLogic] = useState<AdvancedLogic>('AND');
  const [drafts, setDrafts] = useState<DraftCondition[]>([]);
  const [attrsByModel, setAttrsByModel] = useState<Record<string, AttrFieldType[]>>({});
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [saving, setSaving] = useState(false);

  const choices = useMemo(
    () => buildPathChoices(modelId, edges, relationName(assoTypes), modelName(models)),
    [modelId, edges, assoTypes, models],
  );

  useEffect(() => {
    if (!open) return;
    setLogic(applied?.logic || 'AND');
    setDrafts(toDrafts(applied));
  }, [open, applied]);

  useEffect(() => {
    setAttrsByModel((current) => ({ ...current, [modelId]: searchableAttrs(attrList) }));
  }, [modelId, attrList]);

  useEffect(() => {
    const missing = [...new Set(drafts.map((item) => choiceOf(choices, item.path)?.endModelId).filter(Boolean) as string[])]
      .filter((id) => id !== modelId && !attrsByModel[id]);
    if (!missing.length) return;
    missing.forEach((id) => {
      getModelAttrList(id).then((attrs: AttrFieldType[]) => {
        setAttrsByModel((current) => ({ ...current, [id]: searchableAttrs(attrs || []) }));
      }).catch(() => {
        setAttrsByModel((current) => ({ ...current, [id]: [] }));
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drafts, choices, modelId, attrsByModel]);

  const updateDraft = (key: string, patch: Partial<DraftCondition>) => {
    setDrafts((current) => current.map((item) => (item.key === key ? { ...item, ...patch } : item)));
  };

  const addCondition = () => {
    setDrafts((current) => [...current, { key: newKey(), path: [], field: '', type: 'str=', value: '' }]);
  };

  const payload = (): AdvancedFilterValue | null => {
    if (!drafts.length) return null;
    return {
      logic,
      conditions: drafts.map(({ key: _key, ...condition }) => condition),
    };
  };

  const apply = () => {
    for (const [index, condition] of drafts.entries()) {
      const missingValue = operatorNeedsValue(condition.type)
        && (condition.type === 'time' ? !condition.start || !condition.end : condition.value === '' || condition.value == null);
      if (!condition.field || !condition.type || missingValue) {
        message.warning(t('AdvancedFilter.conditionIncomplete').replace('{n}', String(index + 1)));
        return;
      }
    }
    onApply(payload());
  };

  const save = async () => {
    if (!saveName.trim()) {
      message.warning(t('FilterBar.filterNameRequired'));
      return;
    }
    setSaving(true);
    try {
      const allSavedFilters = (userConfigs.cmdb_saved_filters || {}) as SavedFiltersConfigValue;
      const current = allSavedFilters[modelId] || [];
      const updated = {
        ...allSavedFilters,
        [modelId]: [...current, {
          id: newKey(),
          name: saveName.trim(),
          filters: queryList,
          advanced_filter: payload(),
        }],
      };
      await saveFilters(SAVED_FILTERS_CONFIG_KEY, updated, !userConfigs.cmdb_saved_filters);
      updateUserConfig(SAVED_FILTERS_CONFIG_KEY, updated);
      message.success(t('FilterBar.saveSuccess'));
      setSaveOpen(false);
    } catch {
      message.error(t('FilterBar.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Drawer
        title={(
          <div>
            <div>{t('AdvancedFilter.title')}</div>
            <div className="mt-1 text-xs font-normal text-[var(--color-text-3)]">{t('AdvancedFilter.subtitle')}</div>
          </div>
        )}
        open={open}
        width={640}
        onClose={onClose}
        footer={(
          <div className="flex justify-end gap-2">
            <Button onClick={() => setDrafts([])}>{t('AdvancedFilter.reset')}</Button>
            <Button onClick={() => { setSaveName(''); setSaveOpen(true); }}>{t('AdvancedFilter.save')}</Button>
            <Button type="primary" onClick={apply}>{t('AdvancedFilter.apply')}</Button>
          </div>
        )}
      >
        <div className="mb-4">
          <div className="mb-1 text-sm text-[var(--color-text-1)]">{t('AdvancedFilter.scope')}</div>
          <div className="mb-2 text-xs text-[var(--color-text-3)]">{t('AdvancedFilter.scopeHint')}</div>
          <ScopeLegend />
        </div>
        <div className="mb-3 flex items-center justify-between gap-3">
          <span className="text-sm text-[var(--color-text-1)]">{t('AdvancedFilter.conditionGroup')}</span>
          <div className="flex items-center gap-2">
            <Button type={logic === 'AND' ? 'primary' : 'default'} onClick={() => setLogic('AND')}>{t('AdvancedFilter.and')}</Button>
            <Button type={logic === 'OR' ? 'primary' : 'default'} onClick={() => setLogic('OR')}>{t('AdvancedFilter.or')}</Button>
          </div>
        </div>
        {logic === 'AND' ? <div className="mb-3 text-xs text-[var(--color-text-3)]">{t('AdvancedFilter.andHint')}</div> : null}
        <div className="flex flex-col gap-3">
          {drafts.map((condition, index) => {
            const endModelId = choiceOf(choices, condition.path)?.endModelId;
            return (
              <ConditionCard
                key={condition.key}
                index={index}
                condition={condition}
                choices={choices}
                attrs={attrsByModel[endModelId || modelId] || []}
                endModelName={endModelId && endModelId !== modelId ? modelName(models)(endModelId) : ''}
                userList={userList}
                onChange={(patch) => updateDraft(condition.key, patch)}
                onRemove={() => setDrafts((current) => current.filter((item) => item.key !== condition.key))}
              />
            );
          })}
        </div>
        <Button className="mt-3" block onClick={addCondition}>{`+ ${t('AdvancedFilter.addCondition')}`}</Button>
      </Drawer>
      <Modal
        title={t('AdvancedFilter.save')}
        open={saveOpen}
        confirmLoading={saving}
        onOk={save}
        onCancel={() => setSaveOpen(false)}
      >
        <Input value={saveName} onChange={(event) => setSaveName(event.target.value)} placeholder={t('FilterBar.filterName')} />
      </Modal>
    </>
  );
}

function scopeDepth(path: string[]): 0 | 1 | 2 {
  if (path.length >= 2) return 2;
  if (path.length === 1) return 1;
  return 0;
}

function scopeLabelKey(depth: 0 | 1 | 2) {
  if (depth === 0) return 'AdvancedFilter.currentModel';
  if (depth === 1) return 'AdvancedFilter.firstHop';
  return 'AdvancedFilter.secondHop';
}

const SCOPE_TONE: Record<0 | 1 | 2, string> = {
  0: 'border-[var(--color-primary)] bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg-1))] text-[var(--color-primary)]',
  1: 'border-[var(--color-warning)] bg-[color-mix(in_srgb,var(--color-warning)_12%,var(--color-bg-1))] text-[var(--color-warning)]',
  2: 'border-[var(--color-success)] bg-[color-mix(in_srgb,var(--color-success)_12%,var(--color-bg-1))] text-[var(--color-success)]',
};

function ScopeLegend() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      {([0, 1, 2] as const).map((item, index) => (
        <React.Fragment key={item}>
          {index > 0 ? <span className="text-[var(--color-text-3)]">&gt;</span> : null}
          <span className={`rounded border px-2 py-1 ${SCOPE_TONE[item]}`}>{t(scopeLabelKey(item))}</span>
        </React.Fragment>
      ))}
    </div>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <div className="mb-1 text-xs text-[var(--color-text-3)]">{children}</div>;
}

function ConditionCard({
  index,
  condition,
  choices,
  attrs,
  endModelName,
  userList,
  onChange,
  onRemove,
}: {
  index: number;
  condition: DraftCondition;
  choices: PathChoice[];
  attrs: AttrFieldType[];
  endModelName: string;
  userList: UserItem[];
  onChange: (patch: Partial<DraftCondition>) => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  const depth = scopeDepth(condition.path);
  const choice = choiceOf(choices, condition.path);
  const pathGroups = ([0, 1, 2] as const).map((item) => ({
    label: t(scopeLabelKey(item)),
    options: (item === 0
      ? [{ label: t('AdvancedFilter.currentModel'), value: JSON.stringify([]) }]
      : choices.filter((entry) => entry.depth === item).map((entry) => ({
        label: entry.label,
        value: JSON.stringify(entry.path),
      }))),
  })).filter((group) => group.options.length);
  const attr = attrs.find((item) => item.attr_id === condition.field);
  const operators = operatorsFor(attr?.attr_type || 'str');
  const operator = operators.find((item) => item.value === condition.type);
  const summary = summarizeCondition(
    choice?.label || t('AdvancedFilter.currentModel'),
    attr?.attr_name || condition.field || t('AdvancedFilter.field'),
    operator?.label || condition.type,
    conditionValueText(condition),
  );
  return (
    <div className="rounded border border-[var(--color-border-2)] p-3">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="mb-1 flex items-center gap-2">
            <span className={`rounded border px-1.5 py-0.5 text-xs ${SCOPE_TONE[depth]}`}>{t(scopeLabelKey(depth))}</span>
            <span className="text-xs text-[var(--color-text-3)]">
              {t('AdvancedFilter.condition').replace('{n}', String(index + 1))}
            </span>
          </div>
          <div className="truncate text-sm text-[var(--color-text-1)]">{summary}</div>
        </div>
        <Button type="link" size="small" onClick={onRemove}>{t('common.delete')}</Button>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <FieldLabel>{t('AdvancedFilter.path')}</FieldLabel>
          <Select
            className="w-full"
            showSearch
            optionFilterProp="label"
            value={JSON.stringify(condition.path)}
            options={pathGroups}
            onChange={(value) => onChange({ path: JSON.parse(value), field: '', type: 'str=', value: '' })}
          />
        </div>
        <div>
          <FieldLabel>{endModelName ? `${endModelName}${t('AdvancedFilter.field')}` : t('AdvancedFilter.field')}</FieldLabel>
          <Select
            className="w-full"
            showSearch
            optionFilterProp="label"
            value={condition.field || undefined}
            placeholder={t('AdvancedFilter.field')}
            options={attrs.map((item) => ({ label: item.attr_name, value: item.attr_id }))}
            onChange={(value) => {
              const next = attrs.find((item) => item.attr_id === value);
              onChange({ field: value, type: operatorsFor(next?.attr_type || 'str')[0].value, value: '' });
            }}
          />
        </div>
        <div>
          <FieldLabel>{t('AdvancedFilter.operator')}</FieldLabel>
          <Select
            className="w-full"
            value={condition.type}
            options={operators}
            onChange={(value) => onChange({ type: value, value: '', start: undefined, end: undefined })}
          />
        </div>
        <div>
          <FieldLabel>{t('AdvancedFilter.value')}</FieldLabel>
          {operatorNeedsValue(condition.type) ? (
            <ValueEditor attr={attr} condition={condition} userList={userList} onChange={onChange} />
          ) : <Input disabled value={operator?.label || ''} />}
        </div>
      </div>
    </div>
  );
}

function ValueEditor({
  attr,
  condition,
  userList,
  onChange,
}: {
  attr?: AttrFieldType;
  condition: DraftCondition;
  userList: UserItem[];
  onChange: (patch: Partial<DraftCondition>) => void;
}) {
  const { t } = useTranslation();
  if (condition.type === 'time') {
    return (
      <DatePicker.RangePicker
        showTime
        className="w-full"
        format="YYYY-MM-DD HH:mm"
        value={[
          condition.start ? dayjs(condition.start) : null,
          condition.end ? dayjs(condition.end) : null,
        ]}
        onChange={(values) => onChange({
          start: values?.[0]?.format('YYYY-MM-DD HH:mm'),
          end: values?.[1]?.format('YYYY-MM-DD HH:mm'),
        })}
      />
    );
  }
  if (condition.type === 'time<' || condition.type === 'time>') {
    return (
      <DatePicker
        showTime
        className="w-full"
        format="YYYY-MM-DD HH:mm"
        value={typeof condition.value === 'string' && condition.value ? dayjs(condition.value) : null}
        onChange={(value) => onChange({ value: value?.format('YYYY-MM-DD HH:mm') || '' })}
      />
    );
  }
  if (attr?.attr_type === 'int' || attr?.attr_type === 'float') {
    return (
      <InputNumber
        className="w-full"
        value={typeof condition.value === 'number' ? condition.value : undefined}
        onChange={(value) => onChange({ value: value ?? '' })}
      />
    );
  }
  if (attr?.attr_type === 'enum' || attr?.attr_type === 'tag' || condition.type.startsWith('list')) {
    return (
      <Select
        mode="multiple"
        className="w-full"
        options={attr?.attr_type === 'user'
          ? userList.map((user) => ({ label: user.username, value: user.id }))
          : optionItems(attr?.option || [])}
        value={Array.isArray(condition.value) ? condition.value : []}
        onChange={(value) => onChange({ value })}
      />
    );
  }
  if (attr?.attr_type === 'organization') {
    const selected = Array.isArray(condition.value) ? condition.value : [];
    return (
      <GroupTreeSelector
        value={selected.map(Number).filter((item) => !Number.isNaN(item))}
        onChange={(value) => onChange({ value: Array.isArray(value) ? value : value == null ? [] : [value] })}
      />
    );
  }
  if (attr?.attr_type === 'bool') {
    return (
      <Select
        options={[{ label: 'Yes', value: true }, { label: 'No', value: false }]}
        value={typeof condition.value === 'boolean' ? condition.value : undefined}
        onChange={(value) => onChange({ value })}
      />
    );
  }
  return (
    <Input
      placeholder={t('FilterBar.pleaseEnterValue')}
      value={typeof condition.value === 'string' ? condition.value : ''}
      onChange={(event) => onChange({ value: event.target.value })}
    />
  );
}

function useModelEdges(modelId: string, active: boolean) {
  const { getModelAssociations } = useModelApi();
  const [edges, setEdges] = useState<Record<string, AssocEdge[]>>({});
  useEffect(() => {
    if (!active || !modelId) return undefined;
    let cancelled = false;
    (async () => {
      const first = ((await getModelAssociations(modelId)) || []) as AssocEdge[];
      const map: Record<string, AssocEdge[]> = { [modelId]: first };
      const nextIds = [...new Set(first.map((edge) => otherModelId(edge, modelId)).filter(Boolean))] as string[];
      await Promise.all(nextIds.map(async (id) => {
        map[id] = ((await getModelAssociations(id)) || []) as AssocEdge[];
      }));
      if (!cancelled) setEdges(map);
    })().catch(() => {
      if (!cancelled) setEdges({});
    });
    return () => {
      cancelled = true;
    };
    // getModelAssociations 每次渲染都是新函数，只按模型重新加载。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, modelId]);
  return edges;
}

function relationName(assoTypes: AssoTypeItem[]) {
  return (asstId?: string) => assoTypes.find((item) => item.asst_id === asstId)?.asst_name || '';
}

function modelName(models: ModelItem[]) {
  return (id: string) => models.find((item) => item.model_id === id)?.model_name || id;
}

function choiceOf(choices: PathChoice[], path: string[]) {
  return choices.find((item) => JSON.stringify(item.path) === JSON.stringify(path));
}
