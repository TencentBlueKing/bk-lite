'use client';

import { Button, Input, Popconfirm, Select, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';

interface FieldDef {
  key: string;
  name: string;
}

interface ConditionValue {
  op: string;
  value: string;
}

interface DecisionRules {
  condition_fields: FieldDef[];
  result_fields: FieldDef[];
  rows: Array<{ conditions: Record<string, ConditionValue | string>; results: Record<string, string> }>;
}

const OPS = [
  { value: 'eq', labelKey: 'itsm.rule.eq' },
  { value: 'ne', labelKey: 'itsm.rule.ne' },
  { value: 'contains', labelKey: 'itsm.rule.contains' },
  { value: 'gt', labelKey: 'itsm.rule.gt' },
  { value: 'lt', labelKey: 'itsm.rule.lt' },
  { value: 'empty', labelKey: 'itsm.rule.emptyOp' },
];

const conditionOf = (raw: ConditionValue | string | undefined): ConditionValue => {
  if (raw && typeof raw === 'object') {
    return { op: raw.op || 'eq', value: raw.value || '' };
  }
  return { op: 'eq', value: typeof raw === 'string' ? raw : '' };
};

interface DecisionItem {
  id: number;
  name: string;
  workflow_id: number | null;
  rules: DecisionRules | Array<unknown>;
}

const emptyRules = (priority: string, group: string): DecisionRules => ({
  condition_fields: [{ key: 'priority', name: priority }],
  result_fields: [{ key: 'group', name: group }],
  rows: [{ conditions: {}, results: {} }],
});

const asRules = (rules: DecisionItem['rules'], priority: string, group: string): DecisionRules => {
  if (rules && !Array.isArray(rules) && rules.condition_fields) {
    return rules;
  }
  return emptyRules(priority, group);
};

export default function Page() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [items, setItems] = useState<DecisionItem[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<DecisionItem | null>(null);
  const [name, setName] = useState('');
  const blankRules = () => emptyRules(t('itsm.ticket.priority'), t('itsm.admin.groups'));
  const [rules, setRules] = useState<DecisionRules>(blankRules);
  const [reference, setReference] = useState<DecisionItem | null>(null);

  const load = useCallback(async () => {
    const data = await api.listResources('decisions') as { items?: DecisionItem[] };
    setItems(data.items || []);
  }, [api.listResources]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const start = (item?: DecisionItem) => {
    setEditing(item || null);
    setName(item?.name || '');
    setRules(item ? asRules(item.rules, t('itsm.ticket.priority'), t('itsm.admin.groups')) : blankRules());
    setOpen(true);
  };

  const save = async () => {
    const body = { name, rules };
    if (editing) {
      await api.updateResource('decisions', editing.id, body);
    } else {
      await api.createResource('decisions', body);
    }
    setOpen(false);
    message.success(editing ? t('itsm.portal.saved') : t('itsm.portal.created'));
    await load();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.rule.decision')}</div>
        <Button type="primary" onClick={() => start()}>{t('itsm.common.create')}</Button>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <CustomTable
          rowKey="id"
          dataSource={items}
          locale={{ emptyText: t('itsm.rule.emptyDecision') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name' },
            {
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: DecisionItem) => (
                <span className="inline-flex gap-2">
                  <Button type="link" size="small" onClick={() => start(item)}>{t('itsm.common.edit')}</Button>
                  <Button type="link" size="small" onClick={() => setReference(item)}>{t('itsm.rule.reference')}</Button>
                  <Popconfirm title={t('itsm.rule.deleteDecision')} onConfirm={() => { void api.deleteResource('decisions', item.id).then(load); }}>
                    <Button type="link" size="small" danger>{t('itsm.common.delete')}</Button>
                  </Popconfirm>
                </span>
              ),
            },
          ]}
        />
      </div>
      <OperateModal title={editing ? t('itsm.rule.editDecision') : t('itsm.rule.newDecision')} open={open} onCancel={() => setOpen(false)} onOk={() => { void save(); }} width={720}>
        <div className="flex flex-col gap-3 text-sm">
          <FieldRow label={t('itsm.portal.name')}>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </FieldRow>
          <div className="text-xs font-medium text-[var(--color-text-2)]">{t('itsm.rule.conditionFields')}</div>
          {rules.condition_fields.map((field, index) => (
            <div key={`c-${index}`} className="flex gap-2">
              <Input placeholder={t('itsm.rule.fieldKey')} value={field.key} onChange={(event) => setRules({ ...rules, condition_fields: rules.condition_fields.map((item, itemIndex) => itemIndex === index ? { ...item, key: event.target.value } : item) })} />
              <Input placeholder={t('itsm.rule.fieldName')} value={field.name} onChange={(event) => setRules({ ...rules, condition_fields: rules.condition_fields.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item) })} />
            </div>
          ))}
          <Button onClick={() => setRules({ ...rules, condition_fields: [...rules.condition_fields, { key: '', name: '' }] })}>{t('itsm.rule.addCondition')}</Button>
          <div className="text-xs font-medium text-[var(--color-text-2)]">{t('itsm.rule.resultFields')}</div>
          {rules.result_fields.map((field, index) => (
            <div key={`r-${index}`} className="flex gap-2">
              <Input placeholder={t('itsm.rule.fieldKey')} value={field.key} onChange={(event) => setRules({ ...rules, result_fields: rules.result_fields.map((item, itemIndex) => itemIndex === index ? { ...item, key: event.target.value } : item) })} />
              <Input placeholder={t('itsm.rule.fieldName')} value={field.name} onChange={(event) => setRules({ ...rules, result_fields: rules.result_fields.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item) })} />
            </div>
          ))}
          <Button onClick={() => setRules({ ...rules, result_fields: [...rules.result_fields, { key: '', name: '' }] })}>{t('itsm.rule.addResult')}</Button>
          <div className="text-xs font-medium text-[var(--color-text-2)]">{t('itsm.rule.ruleHint')}</div>
          {rules.rows.map((row, index) => (
            <div key={`row-${index}`} className="grid grid-cols-2 gap-2 rounded border border-[var(--color-border)] p-2">
              {rules.condition_fields.map((field) => {
                const current = conditionOf(row.conditions[field.key]);
                return (
                  <div key={field.key} className="flex gap-2">
                    <Select className="w-28" value={current.op} options={OPS.map((item) => ({ value: item.value, label: t(item.labelKey) }))} onChange={(op) => {
                      const rows = rules.rows.map((item, itemIndex) => itemIndex === index ? { ...item, conditions: { ...item.conditions, [field.key]: { ...current, op } } } : item);
                      setRules({ ...rules, rows });
                    }} />
                    <Input placeholder={t('itsm.rule.conditionValue', undefined, { name: field.name || field.key })} value={current.value} disabled={current.op === 'empty'} onChange={(event) => {
                      const rows = rules.rows.map((item, itemIndex) => itemIndex === index ? { ...item, conditions: { ...item.conditions, [field.key]: { ...current, value: event.target.value } } } : item);
                      setRules({ ...rules, rows });
                    }} />
                  </div>
                );
              })}
              {rules.result_fields.map((field) => (
                <Input key={field.key} placeholder={t('itsm.rule.resultValue', undefined, { name: field.name || field.key })} value={row.results[field.key] || ''} onChange={(event) => {
                  const rows = rules.rows.map((item, itemIndex) => itemIndex === index ? { ...item, results: { ...item.results, [field.key]: event.target.value } } : item);
                  setRules({ ...rules, rows });
                }} />
              ))}
            </div>
          ))}
          <Button onClick={() => setRules({ ...rules, rows: [...rules.rows, { conditions: {}, results: {} }] })}>{t('itsm.rule.addRow')}</Button>
        </div>
      </OperateModal>
      <OperateModal title={t('itsm.rule.reference')} open={Boolean(reference)} footer={null} onCancel={() => setReference(null)}>
        {reference?.workflow_id ? t('itsm.rule.referenced', undefined, { id: String(reference.workflow_id) }) : t('itsm.rule.notReferenced')}
      </OperateModal>
    </div>
  );
}
