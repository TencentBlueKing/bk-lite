'use client';

import { invalidMatchRules } from '@/app/alarm/utils/multivalueRules';

import React, { useEffect, useState } from 'react';
import { Drawer, Form, Input, Select, AutoComplete, Button, Space, message, Radio } from 'antd';
import type { FormInstance } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useSettingApi } from '@/app/alarm/api/settings';
import { EnrichmentRuleListItem } from '@/app/alarm/types/settings';
import { ruleList } from '@/app/alarm/constants/settings';
import MatchRule from '@/app/alarm/(pages)/settings/components/matchRule';

interface OperateModalProps {
  open: boolean;
  onClose: () => void;
  currentRow?: EnrichmentRuleListItem | null;
  onSuccess?: () => void;
}

// 默认展示一条起始匹配条件行（参考相关性规则，避免空白难理解）；
// 用户不填条件值则提交时被清理为空 = 对全部事件生效。
const DEFAULT_MATCH_RULES = [
  [{ key: 'title', operator: 'eq', value: '' }],
];

function followSourceAlias(source: string, currentAs: string, previousSource: string) {
  if (!currentAs || currentAs === previousSource) return source;
  return currentAs;
}

function fillProjectionAlias(
  form: FormInstance,
  index: number,
  nextSource: string,
  previousSource: string
) {
  const rows = [...(form.getFieldValue('output_projection') || [])];
  const row = { ...(rows[index] || {}), source: nextSource };
  const currentAs = String(row.as || '');
  const nextAs = followSourceAlias(nextSource, currentAs, previousSource);
  if (row.as === nextAs && row.source === nextSource) return;
  rows[index] = { ...row, as: nextAs };
  form.setFieldsValue({ output_projection: rows });
}

function projectionAliases(rows: { source?: string; as?: string }[] | undefined) {
  const options: { value: string; label: string }[] = [];
  const seen = new Set<string>();
  for (const row of rows || []) {
    const source = String(row?.source || '').trim();
    if (!source) continue;
    const alias = String(row?.as || source).trim();
    if (!alias || seen.has(alias)) continue;
    seen.add(alias);
    options.push({
      value: alias,
      label: alias === source ? alias : `${alias} (${source})`,
    });
  }
  return options;
}

interface ContextFieldOption {
  value: string;
  label: string;
}

interface ContextFieldOptionGroup {
  label: string;
  options: ContextFieldOption[];
}

function flattenContextFieldOptions(groups: ContextFieldOptionGroup[]) {
  const items: ContextFieldOption[] = [];
  for (const group of groups || []) {
    for (const item of group.options || []) {
      if (!item?.value) continue;
      items.push({ value: item.value, label: String(item.label || item.value) });
    }
  }
  return items;
}

function displayProjectionSource(source: string, groups: ContextFieldOptionGroup[]) {
  const key = String(source || '');
  if (!key) return key;
  const hit = flattenContextFieldOptions(groups).find((item) => item.value === key);
  return hit?.label || key;
}

function resolveProjectionSource(text: string, groups: ContextFieldOptionGroup[]) {
  const raw = String(text || '');
  const trimmed = raw.trim();
  if (!trimmed) return raw;
  const items = flattenContextFieldOptions(groups);
  const byValue = items.find((item) => item.value === trimmed);
  if (byValue) return byValue.value;
  const byLabel = items.find((item) => item.label === trimmed);
  if (byLabel) return byLabel.value;
  return raw;
}

const ProjectionSourceAutoComplete: React.FC<{
  value?: string;
  onChange?: (value: string) => void;
  aliasIndex: number;
  options: ContextFieldOptionGroup[];
  placeholder?: string;
}> = ({ value, onChange, aliasIndex, options, placeholder }) => {
  const form = Form.useFormInstance();
  const fieldItems = flattenContextFieldOptions(options);
  return (
    <AutoComplete
      allowClear
      value={displayProjectionSource(value || '', options)}
      options={options}
      placeholder={placeholder}
      style={{ width: 280 }}
      filterOption={(input, option) => {
        const exactSelected = fieldItems.some(
          (item) => item.value === input || item.label === input
        );
        if (exactSelected) return true;
        const q = input.toLowerCase();
        const candidate = option as { value?: string; label?: unknown } | undefined;
        return (
          String(candidate?.value ?? '').toLowerCase().includes(q) ||
          String(candidate?.label ?? '').toLowerCase().includes(q)
        );
      }}
      onChange={(nextValue) => {
        const next = resolveProjectionSource(String(nextValue || ''), options);
        const previous = String(value || '');
        onChange?.(next);
        window.setTimeout(() => {
          fillProjectionAlias(form, aliasIndex, next, previous);
        }, 0);
      }}
      onSelect={(nextValue) => {
        const next = resolveProjectionSource(String(nextValue || ''), options);
        const previous = String(value || '');
        window.setTimeout(() => {
          fillProjectionAlias(form, aliasIndex, next, previous);
        }, 0);
      }}
    />
  );
};

const OperateModal: React.FC<OperateModalProps> = ({
  open,
  onClose,
  currentRow,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { createEnrichment, updateEnrichment, getCmdbContextFields } = useSettingApi();
  const [form] = Form.useForm();
  const outputProjection = Form.useWatch('output_projection', form) || [];
  const ownerFieldOptions = projectionAliases(outputProjection);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [filterType, setFilterType] = useState<'all' | 'filter'>('all');
  const [contextFieldOptions, setContextFieldOptions] = useState<
    ContextFieldOptionGroup[]
  >([]);
  const isEdit = !!currentRow;

  const handleClose = () => {
    form.resetFields();
    setFilterType('all');
    onClose();
  };

  useEffect(() => {
    if (!open) return;
    if (isEdit && currentRow) {
      form.setFieldsValue({
        name: currentRow.name,
        provider_type: currentRow.provider_type || 'cmdb',
        namespace: currentRow.namespace,
        match_rules: currentRow.match_rules?.length
          ? currentRow.match_rules
          : DEFAULT_MATCH_RULES,
        on_multiple: currentRow.on_multiple || 'first',
        input_binding: Object.entries(currentRow.input_binding || {}).map(
          ([param, field]) => ({ param, field })
        ),
        output_projection: (currentRow.output_projection || []).map((p) => ({
          source: p.source,
          as: p.as || p.source || '',
        })),
        owner_fields: currentRow.provider_config?.owner_fields?.length
          ? currentRow.provider_config.owner_fields
          : [],
      });
      setFilterType(currentRow.match_rules?.length ? 'filter' : 'all');
    } else {
      form.resetFields();
      setFilterType('all');
      form.setFieldsValue({
        provider_type: 'cmdb',
        namespace: 'cmdb_custom',
        match_rules: DEFAULT_MATCH_RULES,
        on_multiple: 'first',
        input_binding: [
          { param: 'model_id', field: 'resource_type' },
          { param: 'inst_uuid', field: 'resource_id' },
        ],
        output_projection: [{ source: 'owner', as: 'owner' }],
        owner_fields: [],
      });
    }
  }, [open, isEdit, currentRow, form]);

  useEffect(() => {
    if (!open || typeof getCmdbContextFields !== 'function') return;
    let cancelled = false;
    getCmdbContextFields()
      .then((data: { groups?: { model_id: string; model_name?: string; fields?: { source: string; attr_name?: string }[] }[] }) => {
        if (cancelled) return;
        setContextFieldOptions(
          (data?.groups || []).map((group) => ({
            label: group.model_name || group.model_id,
            options: (group.fields || []).map((field) => ({
              value: field.source,
              label: field.attr_name
                ? `${field.attr_name} (${field.source})`
                : field.source,
            })),
          }))
        );
      })
      .catch(() => {
        if (!cancelled) setContextFieldOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const onFinish = async (values: any) => {
    setSubmitLoading(true);
    try {
      const input_binding: Record<string, string> = {};
      (values.input_binding || []).forEach((r: any) => {
        if (r.param && r.field) input_binding[r.param] = r.field;
      });
      const output_projection = (values.output_projection || [])
        .filter((r: any) => r.source)
        .map((r: any) =>
          r.as ? { source: r.source, as: r.as } : { source: r.source }
        );
      const projectionAliasSet = new Set(
        output_projection.map((item: { source: string; as?: string }) => item.as || item.source)
      );

      const match_rules = filterType === 'filter' ? values.match_rules : [];


      const payload = {
        name: values.name,
        is_active: currentRow?.is_active ?? true,
        provider_type: values.provider_type,
        namespace: values.namespace || '',
        match_rules,
        provider_config: {
          ...(currentRow?.provider_config || {}),
          owner_fields: (values.owner_fields || []).filter((name: string) =>
            projectionAliasSet.has(name)
          ),
        },
        input_binding,
        output_projection,
        on_multiple: values.on_multiple,
      };

      if (isEdit && currentRow) {
        await updateEnrichment(currentRow.id, payload);
      } else {
        await createEnrichment(payload);
      }
      message.success(t('alarmCommon.successOperate'));
      handleClose();
      onSuccess?.();
    } catch {
      message.error(t('alarmCommon.operateFailed'));
    } finally {
      setSubmitLoading(false);
    }
  };

  return (
    <Drawer
      title={
        isEdit
          ? t('common.edit') + (currentRow ? ` - ${currentRow.name}` : '')
          : t('common.addNew')
      }
      placement="right"
      width={720}
      open={open}
      onClose={handleClose}
      maskClosable={false}
      footer={
        <div style={{ textAlign: 'right' }}>
          <Button
            type="primary"
            loading={submitLoading}
            onClick={() => form.submit()}
          >
            {t('common.confirm')}
          </Button>
          <Button style={{ marginLeft: 8 }} onClick={handleClose}>
            {t('common.cancel')}
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
        onValuesChange={(changed) => {
          const changedRows = changed?.output_projection;
          if (!Array.isArray(changedRows)) return;
          changedRows.forEach((row: { source?: string } | undefined, index: number) => {
            if (!row || !Object.prototype.hasOwnProperty.call(row, 'source')) return;
            const source = String(row.source || '');
            const currentAs = String(
              form.getFieldValue(['output_projection', index, 'as']) || ''
            );
            if (source && !currentAs) {
              window.setTimeout(() => {
                fillProjectionAlias(form, index, source, '');
              }, 0);
            }
          });
        }}
      >
        <Form.Item
          name="name"
          label={t('settings.enrichmentName')}
          rules={[{ required: true, message: t('common.inputTip') }]}
        >
          <Input maxLength={100} placeholder={t('common.inputTip')} />
        </Form.Item>

        <Form.Item
          name="provider_type"
          label={t('settings.enrichmentProvider')}
          rules={[{ required: true, message: t('common.selectTip') }]}
        >
          <Select options={[{ label: 'CMDB', value: 'cmdb' }]} />
        </Form.Item>

        <Form.Item
          name="namespace"
          label={t('settings.enrichmentNamespace')}
          tooltip={t('settings.enrichmentNamespaceTip')}
          rules={[{ required: true, message: t('common.inputTip') }]}
        >
          <Input placeholder="cmdb_custom" />
        </Form.Item>

        <Form.Item
          label={t('settings.enrichmentMatchRules')}
          tooltip={t('settings.enrichmentMatchRulesTip')}
          className="mb-2"
        >
          <Radio.Group
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            size="small"
          >
            <Radio.Button value="all">
              {t('settings.enrichmentScopeAll')}
            </Radio.Button>
            <Radio.Button value="filter">
              {t('settings.enrichmentScopeFilter')}
            </Radio.Button>
          </Radio.Group>
        </Form.Item>
        {filterType === 'filter' && (
          <Form.Item name="match_rules" className="mb-4" rules={[{validator: (_, value) => invalidMatchRules(value, false, "enrichment") ? Promise.reject(new Error(t('common.inputTip'))) : Promise.resolve()}]}>
            <MatchRule scope="enrichment" levelType="event" />
          </Form.Item>
        )}

        <Form.Item label={t('settings.enrichmentInputBinding')} required>
          <Form.List name="input_binding">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Space key={key} align="baseline" className="flex mb-2">
                    <Form.Item
                      {...rest}
                      name={[name, 'param']}
                      rules={[{ required: true, message: t('common.inputTip') }]}
                      noStyle
                    >
                      <Input
                        placeholder={t('settings.enrichmentBindParam')}
                        style={{ width: 280 }}
                      />
                    </Form.Item>
                    <Form.Item
                      {...rest}
                      name={[name, 'field']}
                      rules={[{ required: true, message: t('common.selectTip') }]}
                      noStyle
                    >
                      <Select
                        showSearch
                        optionFilterProp="label"
                        placeholder={t('settings.enrichmentBindField')}
                        style={{ width: 280 }}
                        options={ruleList.map((r) => ({
                          label: r.verbose_name,
                          value: r.name,
                        }))}
                      />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Button
                  type="dashed"
                  onClick={() => add()}
                  icon={<PlusOutlined />}
                  block
                >
                  {t('common.addNew')}
                </Button>
              </>
            )}
          </Form.List>
        </Form.Item>

        <Form.Item
          label={t('settings.enrichmentOutputProjection')}
          tooltip={t('settings.enrichmentContextFieldsTip')}
          required
        >
          <Form.List name="output_projection">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Space key={key} align="baseline" className="flex mb-2">
                    <Form.Item
                      {...rest}
                      name={[name, 'source']}
                      rules={[{ required: true, message: t('common.inputTip') }]}
                      noStyle
                    >
                      <ProjectionSourceAutoComplete
                        aliasIndex={name}
                        options={contextFieldOptions}
                        placeholder={t('settings.enrichmentProjSource')}
                      />
                    </Form.Item>
                    <Form.Item {...rest} name={[name, 'as']} noStyle>
                      <Input
                        placeholder={t('settings.enrichmentProjAs')}
                        style={{ width: 280 }}
                      />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Button
                  type="dashed"
                  onClick={() => add({ source: '', as: '' })}
                  icon={<PlusOutlined />}
                  block
                >
                  {t('common.addNew')}
                </Button>
              </>
            )}
          </Form.List>
        </Form.Item>

        <Form.Item
          name="owner_fields"
          label={t('settings.enrichmentOwnerFields')}
          extra={t('settings.enrichmentOwnerFieldsTip')}
        >
          <Select
            mode="multiple"
            allowClear
            options={ownerFieldOptions}
            placeholder={t('common.selectTip')}
          />
        </Form.Item>
        <Form.Item label={t('settings.enrichmentOwnerTarget')}>
          <Input value={t('settings.enrichmentOwnerTargetValue')} disabled />
        </Form.Item>

        <Form.Item
          name="on_multiple"
          label={t('settings.enrichmentOnMultiple')}
          rules={[{ required: true, message: t('common.selectTip') }]}
        >
          <Select
            options={[
              { label: t('settings.onMultipleFirst'), value: 'first' },
              { label: t('settings.onMultipleMerge'), value: 'merge' },
              { label: t('settings.onMultipleList'), value: 'list' },
            ]}
          />
        </Form.Item>
      </Form>
    </Drawer>
  );
};

export default OperateModal;
