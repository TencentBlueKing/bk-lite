'use client';

import React, { useState } from 'react';
import { Button, Form, Input, message, Popconfirm, Radio, Select } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import type { CredentialFieldKind, CredentialFieldSchema } from '@/components/credential-picker/types';
import { formatVisibleWhen } from '@/components/credential-picker/visibleWhen';
import { parseEnumValues } from '@/components/credential-picker/enumValues';

type ControlKind = CredentialFieldKind | 'textarea';

interface VisibleCondition {
  field: string;
  op: 'eq' | 'ne';
  value: string;
}

interface TypeFieldsDesignerProps {
  value?: CredentialFieldSchema[];
  typeName?: string;
  onChange?: (fields: CredentialFieldSchema[]) => void;
  readOnly?: boolean;
}

const CONTROL_KINDS: ControlKind[] = ['string', 'number', 'secret', 'enum', 'textarea'];

const controlKindOf = (field?: CredentialFieldSchema): ControlKind => {
  if (field?.widget === 'textarea') {
    return 'textarea';
  }
  return field?.kind || 'string';
};

const parseConditions = (field?: CredentialFieldSchema): VisibleCondition[] => {
  if (!field?.visible_when) {
    return [];
  }
  return Object.entries(field.visible_when).map(([id, condition]) => ({
    field: id,
    op: typeof condition === 'string' || condition?.op !== 'ne' ? 'eq' : 'ne',
    value: typeof condition === 'string' ? condition : condition.value,
  }));
};

const TypeFieldsDesigner: React.FC<TypeFieldsDesignerProps> = ({
  value = [],
  typeName,
  onChange,
  readOnly,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [conditions, setConditions] = useState<VisibleCondition[]>([]);
  const kind = Form.useWatch('kind', form) as ControlKind | undefined;

  const commit = (next: CredentialFieldSchema[]) => onChange?.(next);
  const others = value.filter((_, index) => index !== editingIndex);

  const move = (index: number, offset: number) => {
    const target = index + offset;
    if (target < 0 || target >= value.length) {
      return;
    }
    const next = [...value];
    const [item] = next.splice(index, 1);
    next.splice(target, 0, item);
    commit(next);
  };

  const openEditor = (index: number | null) => {
    setEditingIndex(index);
    const current = index === null ? undefined : value[index];
    setConditions(parseConditions(current));
    form.setFieldsValue({
      id: current?.id,
      name: current?.name,
      kind: controlKindOf(current),
      required: Boolean(current?.required),
      defaultValue: current?.default || '',
      values: parseEnumValues(current?.values).join(', '),
    });
    setOpen(true);
  };

  const fieldKindLabel = (record: CredentialFieldSchema) => {
    if (record.widget === 'textarea') {
      return t('system.credential.kinds.textarea', '多行文本');
    }
    return t(`system.credential.kinds.${record.kind}`);
  };

  const fieldExtras = (record: CredentialFieldSchema) => {
    const parts = [
      fieldKindLabel(record),
      record.values?.length ? parseEnumValues(record.values).join(' / ') : '',
      record.default ? t('system.credential.defaultPrefix', '默认 {value}', { value: record.default }) : '',
    ].filter(Boolean);
    return parts.join(' · ');
  };

  const updateCondition = (index: number, patch: Partial<VisibleCondition>) => {
    setConditions((current) => {
      const next = [...current];
      const merged = { ...next[index], ...patch };
      if (patch.field) {
        const dep = others.find((item) => item.id === patch.field);
        const options = parseEnumValues(dep?.values);
        if (dep?.kind === 'enum' && options.length && !options.includes(merged.value)) {
          merged.value = options[0];
        }
      }
      next[index] = merged;
      return next;
    });
  };

  const addCondition = () => {
    if (!others.length) {
      message.warning(t('system.credential.visibleWhenNeedOther', '请先添加并保存其他字段，再设置显示条件'));
      return;
    }
    const first = others[0];
    const firstOptions = parseEnumValues(first.values);
    setConditions((current) => [
      ...current,
      {
        field: first.id,
        op: 'eq',
        value: first.kind === 'enum' && firstOptions.length ? firstOptions[0] : '',
      },
    ]);
  };

  const saveField = async () => {
    const values = await form.validateFields();
    if (editingIndex === null && value.some((item) => item.id === values.id)) {
      message.error(t('system.credential.duplicateFieldId', '字段标识已存在'));
      return;
    }
    for (const condition of conditions) {
      if (!condition.field || !String(condition.value || '').trim()) {
        message.error(t('system.credential.visibleWhenIncomplete', '请为每条显示条件选择字段并填写取值'));
        return;
      }
    }
    const field: CredentialFieldSchema = {
      id: values.id,
      name: values.name,
      kind: values.kind === 'textarea' ? 'string' : values.kind,
      required: Boolean(values.required),
    };
    if (values.kind === 'textarea') {
      field.widget = 'textarea';
    }
    if (values.kind === 'enum') {
      field.values = parseEnumValues(values.values);
    }
    const defaultValue = String(values.defaultValue || '').trim();
    if (defaultValue) {
      field.default = defaultValue;
    }
    if (conditions.length) {
      field.visible_when = Object.fromEntries(
        conditions.map((condition) => [
          condition.field,
          condition.op === 'ne' ? { op: 'ne' as const, value: condition.value.trim() } : condition.value.trim(),
        ]),
      );
    }
    const next = [...value];
    if (editingIndex === null) {
      next.push(field);
    } else {
      next[editingIndex] = field;
    }
    commit(next);
    setOpen(false);
  };

  const titlePrefix = editingIndex === null ? t('system.credential.addField') : t('system.credential.editField');

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <div className="mb-3 flex h-8 shrink-0 items-center justify-between gap-3">
        <h3 className="text-sm font-medium leading-5 text-[var(--color-text-1)]">
          {t('system.credential.fieldDefinition')}
        </h3>
        {readOnly ? null : (
          <Button size="small" onClick={() => openEditor(null)}>
            + {t('system.credential.addField')}
          </Button>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {value.length === 0 ? (
          <div className="flex min-h-[120px] flex-col items-center justify-center rounded-lg bg-[var(--color-fill-1)] px-6 py-10 text-center">
            <p className="mb-0 text-sm leading-6 text-[var(--color-text-3)]">{t('system.credential.fieldEmpty')}</p>
            {readOnly ? null : (
              <p className="mb-0 mt-1 text-xs leading-5 text-[var(--color-text-3)]">{t('system.credential.fieldEmptyHint')}</p>
            )}
          </div>
        ) : (
          <div>
            {value.map((record, index) => {
              const cond = formatVisibleWhen(record);
              const extras = fieldExtras(record);
              return (
                <div
                  key={record.id}
                  className="mb-2 flex gap-3 rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] px-3.5 py-3 last:mb-0 hover:border-[var(--color-border-1)]"
                >
                  <div className="mt-px flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full bg-[var(--color-fill-2)] text-[11px] font-semibold text-[var(--color-text-3)]">
                    {index + 1}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-sm font-semibold text-[var(--color-text-1)]">
                        <span className="min-w-0 truncate">{record.name || record.id}</span>
                        {record.required ? (
                          <span className="inline-flex h-[18px] shrink-0 items-center rounded-[3px] border border-[color-mix(in_srgb,var(--color-fail)_35%,transparent)] bg-[color-mix(in_srgb,var(--color-fail)_8%,var(--color-bg))] px-1 text-[11px] font-medium text-[var(--color-fail)]">
                            {t('system.credential.required')}
                          </span>
                        ) : null}
                      </div>
                      {readOnly ? null : (
                        <div className="flex shrink-0 items-center gap-2.5">
                          <Button
                            type="link"
                            size="small"
                            disabled={index === 0}
                            className="!h-auto !px-0 text-xs text-[var(--color-text-3)]"
                            onClick={() => move(index, -1)}
                          >
                            {t('system.credential.moveUp')}
                          </Button>
                          <Button
                            type="link"
                            size="small"
                            disabled={index === value.length - 1}
                            className="!h-auto !px-0 text-xs text-[var(--color-text-3)]"
                            onClick={() => move(index, 1)}
                          >
                            {t('system.credential.moveDown')}
                          </Button>
                          <Button
                            type="link"
                            size="small"
                            className="!h-auto !px-0 text-xs"
                            onClick={() => openEditor(index)}
                          >
                            {t('common.edit')}
                          </Button>
                          <Popconfirm
                            title={t('common.delConfirm')}
                            onConfirm={() => commit(value.filter((item) => item.id !== record.id))}
                          >
                            <Button type="link" size="small" danger className="!h-auto !px-0 text-xs">
                              {t('common.delete')}
                            </Button>
                          </Popconfirm>
                        </div>
                      )}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-3)]">
                      <code className="rounded-[3px] bg-[var(--color-fill-2)] px-1.5 py-px font-mono text-[11px] text-[var(--color-text-2)]">
                        {record.id}
                      </code>
                      {extras ? <span>{extras}</span> : null}
                    </div>
                    {cond ? (
                      <div className="mt-1.5 text-xs leading-snug text-[var(--color-text-2)]">
                        {t('system.credential.visibleWhenOnly', undefined, { cond })}
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
      <OperateModal
        title={typeName ? `${titlePrefix} · ${typeName}` : titlePrefix}
        open={open}
        okText={editingIndex === null ? t('system.credential.addField') : t('system.credential.saveField', '保存字段')}
        onOk={() => void saveField()}
        onCancel={() => setOpen(false)}
        width={600}
      >
        <Form form={form} layout="vertical" className="pt-1">
          <div className="grid grid-cols-2 gap-3">
            <Form.Item
              name="id"
              label={t('system.credential.fieldKey')}
              extra={<span className="text-xs">{t('system.credential.fieldKeyHint', '字母开头，仅含字母、数字和下划线。')}</span>}
              rules={[{ required: true, pattern: /^[A-Za-z][A-Za-z0-9_]*$/ }]}
            >
              <Input disabled={editingIndex !== null} className="font-mono" placeholder={t('common.inputTip')} />
            </Form.Item>
            <Form.Item name="name" label={t('system.credential.fieldName')} rules={[{ required: true, whitespace: true }]}>
              <Input placeholder={t('common.inputTip')} />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Form.Item name="kind" label={t('system.credential.fieldKind')} rules={[{ required: true }]}>
              <Select
                options={CONTROL_KINDS.map((item) => ({
                  value: item,
                  label: t(`system.credential.kinds.${item}`),
                }))}
              />
            </Form.Item>
            <Form.Item name="defaultValue" label={t('system.credential.fieldDefault', '默认值')}>
              <Input placeholder={t('system.credential.fieldDefaultPlaceholder', '可选')} />
            </Form.Item>
          </div>
          {kind === 'enum' ? (
            <Form.Item
              name="values"
              label={t('system.credential.enumValues')}
              extra={t('system.credential.enumValuesHint')}
              rules={[
                { required: true, whitespace: true },
                {
                  validator: async (_, value) => {
                    if (!parseEnumValues(value).length) {
                      throw new Error(t('system.credential.enumValuesHint'));
                    }
                  },
                },
              ]}
            >
              <Input placeholder={t('system.credential.enumValuesPlaceholder')} />
            </Form.Item>
          ) : null}
          <div className="grid grid-cols-2 gap-3">
            <Form.Item
              name="required"
              label={t('system.credential.fieldRequired', '字段必填')}
              className="!mb-3"
            >
              <Radio.Group>
                <Radio value={true}>{t('common.yes')}</Radio>
                <Radio value={false}>{t('common.no')}</Radio>
              </Radio.Group>
            </Form.Item>
          </div>
          <div className="relative">
            <Button
              size="small"
              htmlType="button"
              className="absolute right-0 top-0 z-10"
              icon={<PlusOutlined />}
              onClick={addCondition}
            >
              {t('system.credential.addCondition', '添加条件')}
            </Button>
            <Form.Item
              label={t('system.credential.visibleWhen')}
              tooltip={{
                title: t(
                  'system.credential.visibleWhenTooltip',
                  '控制此字段何时出现。例如仅当「认证方式 = 密码」时显示密码框。不设置则始终显示；多条条件需同时满足。',
                ),
                overlayInnerStyle: { maxWidth: 366 },
              }}
              className="!mb-0 [&_.ant-form-item-label]:pr-28 [&_.ant-form-item-label]:!pb-3"
            >
            {conditions.length ? (
              <div>
                {conditions.map((condition, index) => {
                  const dep = others.find((item) => item.id === condition.field) || others[0];
                  return (
                    <div key={`${condition.field}-${index}`} className="mb-2 flex items-center gap-2 last:mb-0">
                      <span className="shrink-0 text-xs text-[var(--color-text-3)]">
                        {t('system.credential.visibleWhenWhen', '当')}
                      </span>
                      <div className="w-40 shrink-0">
                        <Select
                          className="w-full"
                          value={condition.field}
                          options={others.map((item) => ({ value: item.id, label: item.name || item.id }))}
                          onChange={(field) => updateCondition(index, { field })}
                        />
                      </div>
                      <div className="w-16 shrink-0">
                        <Select
                          className="w-full"
                          value={condition.op}
                          options={[
                            { value: 'eq', label: '=' },
                            { value: 'ne', label: '≠' },
                          ]}
                          onChange={(op) => updateCondition(index, { op })}
                        />
                      </div>
                      <div className="min-w-0 flex-1">
                        {dep?.kind === 'enum' && parseEnumValues(dep.values).length ? (
                          <Select
                            className="w-full"
                            value={condition.value}
                            options={parseEnumValues(dep.values).map((item) => ({ value: item, label: item }))}
                            onChange={(nextValue) => updateCondition(index, { value: nextValue })}
                          />
                        ) : (
                          <Input
                            className="w-full"
                            value={condition.value}
                            placeholder={t('system.credential.condValuePlaceholder', '输入值')}
                            onChange={(event) => updateCondition(index, { value: event.target.value })}
                          />
                        )}
                      </div>
                      <Button type="link" danger className="!h-auto !px-0 shrink-0" onClick={() => setConditions((current) => current.filter((_, i) => i !== index))}>
                        ✕
                      </Button>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="rounded-lg bg-[var(--color-fill-1)]">
                <CompactEmptyState
                  className="py-6"
                  description={
                    others.length
                      ? t('system.credential.visibleWhenEmpty', '未设置条件，此字段将始终显示')
                      : t('system.credential.visibleWhenNeedOther', '请先添加并保存其他字段，再设置显示条件')
                  }
                />
              </div>
            )}
            </Form.Item>
          </div>
        </Form>
      </OperateModal>
    </div>
  );
};

export default TypeFieldsDesigner;
