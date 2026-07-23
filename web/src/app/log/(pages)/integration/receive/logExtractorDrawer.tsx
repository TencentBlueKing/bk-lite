'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  AutoComplete,
  Button,
  Checkbox,
  Col,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message
} from 'antd';
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  HolderOutlined,
  PlusOutlined
} from '@ant-design/icons';
import useLogApi from '@/app/log/api/integration';
import {
  ExtractorConditionItem,
  ExtractorPublicationStatus,
  ExtractorType,
  LogExtractorDraft,
  LogExtractorPreviewResult,
  LogExtractorRule
} from '@/app/log/types/extractor';
import { useTranslation } from '@/utils/i18n';
import {
  flattenExtractorPaths,
  moveExtractorItem,
  normalizeExtractorSamples,
  reorderExtractorItem,
  shouldShowExtractorHeaderAdd
} from './logExtractorLogic';

interface Props {
  instance: { id: string; name: string; canOperate: boolean } | null;
  open: boolean;
  onClose: () => void;
}

interface FormValue {
  name: string;
  extractor_type: ExtractorType;
  source_field: string;
  target_field?: string;
  delete_source?: boolean;
  condition_mode: 'AND' | 'OR';
  conditions?: ExtractorConditionItem[];
  delimiter?: string;
  index?: number;
  key_value_delimiter?: string;
  field_delimiter?: string;
  field_mapping_text?: string;
  pattern?: string;
  group_mapping_text?: string;
  replacement?: string;
}

const EXTRACTOR_TYPES: ExtractorType[] = [
  'copy',
  'split',
  'kv',
  'regex',
  'regex_replace',
  'json'
];

const OPERATORS: ExtractorConditionItem['op'][] = [
  '==',
  '!=',
  'contains',
  '!contains',
  'startswith',
  'endswith',
  'exists',
  '!exists'
];

const publicationColor: Record<ExtractorPublicationStatus['status'], string> = {
  pending: 'processing',
  generating: 'processing',
  published: 'success',
  failed: 'error'
};

const toFormValue = (rule?: LogExtractorRule): FormValue => {
  const config = rule?.config || {};
  return {
    name: rule?.name || '',
    extractor_type: rule?.extractor_type || 'copy',
    source_field: rule?.source_field || 'message',
    target_field: rule?.target_field || '',
    delete_source: rule?.delete_source || false,
    condition_mode: rule?.condition.mode || 'AND',
    conditions: rule?.condition.conditions || [],
    delimiter: typeof config.delimiter === 'string' ? config.delimiter : '',
    index: typeof config.index === 'number' ? config.index : 0,
    key_value_delimiter:
      typeof config.key_value_delimiter === 'string'
        ? config.key_value_delimiter
        : '=',
    field_delimiter:
      typeof config.field_delimiter === 'string' ? config.field_delimiter : ' ',
    field_mapping_text: JSON.stringify(config.field_mapping || {}, null, 2),
    pattern: typeof config.pattern === 'string' ? config.pattern : '',
    group_mapping_text: JSON.stringify(config.group_mapping || {}, null, 2),
    replacement:
      typeof config.replacement === 'string' ? config.replacement : ''
  };
};

const parseMapping = (value: string | undefined, errorMessage: string) => {
  try {
    const mapping: unknown = JSON.parse(value || '{}');
    if (
      !mapping ||
      typeof mapping !== 'object' ||
      Array.isArray(mapping) ||
      Object.values(mapping).some((target) => typeof target !== 'string')
    ) {
      throw new Error(errorMessage);
    }
    return mapping as Record<string, string>;
  } catch {
    throw new Error(errorMessage);
  }
};

const parseConditionValue = (
  value: ExtractorConditionItem['value']
): ExtractorConditionItem['value'] => {
  if (typeof value !== 'string') return value;
  try {
    const parsed: unknown = JSON.parse(value);
    return parsed === null || ['string', 'number', 'boolean'].includes(typeof parsed)
      ? (parsed as ExtractorConditionItem['value'])
      : value;
  } catch {
    return value;
  }
};

const LogExtractorDrawer = ({ instance, open, onClose }: Props) => {
  const { t } = useTranslation();
  const api = useLogApi();
  const apiRef = useRef(api);
  apiRef.current = api;
  const [form] = Form.useForm<FormValue>();
  const extractorType = Form.useWatch('extractor_type', form);
  const [rules, setRules] = useState<LogExtractorRule[]>([]);
  const [publication, setPublication] =
    useState<ExtractorPublicationStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<LogExtractorRule | null>(null);
  const [samples, setSamples] = useState<Record<string, unknown>[]>([]);
  const [samplesLoading, setSamplesLoading] = useState(false);
  const [samplesError, setSamplesError] = useState(false);
  const [sampleIndex, setSampleIndex] = useState<number | null>(null);
  const [preview, setPreview] = useState<LogExtractorPreviewResult | null>(null);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    if (!instance) return;
    setLoading(true);
    try {
      const data = await apiRef.current.getLogExtractors(instance.id);
      setRules(data.items);
      setPublication(data.publication);
    } finally {
      setLoading(false);
    }
  }, [instance]);

  const loadSamples = useCallback(async () => {
    if (!instance) return;
    setSamplesLoading(true);
    setSamplesError(false);
    try {
      const data = normalizeExtractorSamples(
        await apiRef.current.getLogExtractorSamples(instance.id)
      );
      setSamples(data);
      setSampleIndex(data.length ? 0 : null);
    } catch (error) {
      setSamplesError(true);
      throw error;
    } finally {
      setSamplesLoading(false);
    }
  }, [instance]);

  useEffect(() => {
    if (!open || !instance) return;
    void refresh().catch(() => undefined);
    void loadSamples().catch(() => undefined);
  }, [open, instance, refresh, loadSamples]);

  useEffect(() => {
    if (!open || !instance) return;
    const timer = window.setInterval(() => {
      void apiRef.current
        .getLogExtractorPublicationStatus(instance.id)
        .then(setPublication)
        .catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [open, instance]);

  const fieldOptions = useMemo(
    () =>
      Array.from(
        samples.reduce(
          (paths, sample) => flattenExtractorPaths(sample, '', paths),
          new Set<string>()
        )
      ).map((value) => ({ value })),
    [samples]
  );

  const conditionSummary = (rule: LogExtractorRule) => {
    if (!rule.condition.conditions.length) return t('log.extractor.noCondition');
    return `${rule.condition.mode}: ${rule.condition.conditions
      .map((item) =>
        ['exists', '!exists'].includes(item.op)
          ? `${item.field} ${item.op}`
          : `${item.field} ${item.op} ${JSON.stringify(item.value)}`
      )
      .join(` ${rule.condition.mode} `)}`;
  };

  const targetSummary = (rule: LogExtractorRule) => {
    const mapping =
      rule.extractor_type === 'kv'
        ? rule.config.field_mapping
        : rule.extractor_type === 'regex'
          ? rule.config.group_mapping
          : null;
    if (mapping && typeof mapping === 'object' && !Array.isArray(mapping)) {
      const targets = Object.values(mapping).filter(
        (value): value is string => typeof value === 'string'
      );
      if (targets.length) return targets.join(', ');
    }
    return rule.target_field || t('log.extractor.rootOrSource');
  };

  const openEditor = (rule?: LogExtractorRule) => {
    setEditing(rule || null);
    setPreview(null);
    form.setFieldsValue(toFormValue(rule));
    setEditorOpen(true);
  };

  const buildDraft = (values: FormValue): LogExtractorDraft => {
    let config: Record<string, unknown> = {};
    if (values.extractor_type === 'split') {
      config = { delimiter: values.delimiter, index: Number(values.index) };
    } else if (values.extractor_type === 'kv') {
      config = {
        key_value_delimiter: values.key_value_delimiter,
        field_delimiter: values.field_delimiter,
        field_mapping: parseMapping(
          values.field_mapping_text,
          t('log.extractor.invalidMapping')
        )
      };
    } else if (values.extractor_type === 'regex') {
      config = {
        pattern: values.pattern,
        group_mapping: parseMapping(
          values.group_mapping_text,
          t('log.extractor.invalidMapping')
        )
      };
    } else if (values.extractor_type === 'regex_replace') {
      config = { pattern: values.pattern, replacement: values.replacement };
    }
    return {
      name: values.name,
      collect_instance: instance?.id || '',
      condition: {
        mode: values.condition_mode,
        conditions: (values.conditions || []).map((condition) =>
          ['exists', '!exists'].includes(condition.op)
            ? { field: condition.field, op: condition.op }
            : { ...condition, value: parseConditionValue(condition.value) }
        )
      },
      extractor_type: values.extractor_type,
      source_field: values.source_field,
      target_field: ['kv', 'regex'].includes(values.extractor_type)
        ? null
        : values.target_field || null,
      delete_source: Boolean(values.delete_source),
      config
    };
  };

  const save = async () => {
    if (!instance) return;
    setSaving(true);
    try {
      const draft = buildDraft(await form.validateFields());
      const response = editing
        ? await api.updateLogExtractor(editing.id, draft)
        : await api.createLogExtractor(draft);
      setPublication(response.publication);
      setEditorOpen(false);
      message.success(t('common.saveSuccess'));
      await refresh();
    } catch (error) {
      if (
        error instanceof Error &&
        error.message === t('log.extractor.invalidMapping')
      ) {
        message.error(error.message);
      }
    } finally {
      setSaving(false);
    }
  };

  const remove = async (rule: LogExtractorRule) => {
    setActionLoading(true);
    try {
      await api.deleteLogExtractor(rule.id);
      message.success(t('common.successfullyDeleted'));
      await refresh();
    } finally {
      setActionLoading(false);
    }
  };

  const persistOrder = async (next: LogExtractorRule[]) => {
    if (!instance) return;
    const previous = rules;
    setRules(next);
    setActionLoading(true);
    try {
      const response = await api.reorderLogExtractors(
        instance.id,
        next.map((rule) => rule.id)
      );
      setPublication(response.publication);
    } catch {
      setRules(previous);
    } finally {
      setActionLoading(false);
    }
  };

  const move = async (index: number, offset: -1 | 1) => {
    const next = moveExtractorItem(rules, index, offset);
    if (next) await persistOrder(next);
  };

  const drop = async (targetIndex: number) => {
    if (draggedIndex === null) return;
    const next = reorderExtractorItem(rules, draggedIndex, targetIndex);
    setDraggedIndex(null);
    if (next) await persistOrder(next);
  };

  const runPreview = async () => {
    if (!instance || sampleIndex === null) return;
    try {
      const draft = buildDraft(await form.validateFields());
      const result = await api.previewLogExtractor({
        collect_instance: instance.id,
        event: samples[sampleIndex],
        draft,
        rule_id: editing?.id
      });
      setPreview(result);
    } catch (error) {
      if (
        error instanceof Error &&
        error.message === t('log.extractor.invalidMapping')
      ) {
        message.error(error.message);
      }
    }
  };

  const retry = async () => {
    if (!instance) return;
    setActionLoading(true);
    try {
      const response = await api.retryLogExtractorPublication(instance.id);
      setPublication(response.publication);
      message.success(t('log.extractor.retrySubmitted'));
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <>
      <Drawer
        title={`${t('log.extractor.title')} · ${instance?.name || ''}`}
        width="min(920px, 100vw)"
        open={open}
        onClose={onClose}
        extra={
          <Space>
            {publication?.status === 'failed' && instance?.canOperate && (
              <Button loading={actionLoading} onClick={() => void retry()}>
                {t('log.extractor.retry')}
              </Button>
            )}
            {shouldShowExtractorHeaderAdd(instance?.canOperate, rules.length) && (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                disabled={actionLoading || rules.length >= 20}
                onClick={() => openEditor()}
              >
                {t('log.extractor.add')}
              </Button>
            )}
          </Space>
        }
      >
        {publication && (
          <Alert
            className="mb-[16px]"
            type={publication.status === 'failed' ? 'error' : 'info'}
            showIcon
            message={
              <Space>
                <span>{t('log.extractor.globalStatus')}</span>
                <Tag color={publicationColor[publication.status]}>
                  {t(`log.extractor.${publication.status}`)}
                </Tag>
                <span>
                  {publication.published_generation}/{publication.desired_generation}
                </span>
              </Space>
            }
            description={
              <Space direction="vertical" size={0}>
                <span>{`${t('log.extractor.publishedHint')} ${t('log.extractor.affectedHint')}`}</span>
                {publication.last_published_at && (
                  <span>
                    {t('log.extractor.lastPublishedAt')}: {publication.last_published_at}
                  </span>
                )}
                {publication.last_error && <span>{publication.last_error}</span>}
              </Space>
            }
          />
        )}
        <Table<LogExtractorRule>
          rowKey="id"
          loading={loading}
          dataSource={rules}
          pagination={false}
          locale={{
            emptyText: (
              <Empty description={t('log.extractor.empty')}>
                {instance?.canOperate && (
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    disabled={actionLoading}
                    onClick={() => openEditor()}
                  >
                    {t('log.extractor.add')}
                  </Button>
                )}
              </Empty>
            )
          }}
          columns={[
            { title: t('common.name'), dataIndex: 'name' },
            {
              title: t('common.type'),
              dataIndex: 'extractor_type',
              width: 130
            },
            { title: t('log.extractor.sourceField'), dataIndex: 'source_field' },
            {
              title: t('log.extractor.condition'),
              ellipsis: true,
              render: (_, rule) => conditionSummary(rule)
            },
            {
              title: t('log.extractor.targetField'),
              ellipsis: true,
              render: (_, rule) => targetSummary(rule)
            },
            {
              title: t('common.action'),
              width: 250,
              render: (_, rule, index) => (
                <Space
                  size={0}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={() => void drop(index)}
                >
                  <Button
                    type="text"
                    draggable={Boolean(instance?.canOperate) && !actionLoading}
                    aria-label={t('log.extractor.dragToReorder')}
                    icon={<HolderOutlined />}
                    disabled={actionLoading || !instance?.canOperate}
                    onDragStart={() => setDraggedIndex(index)}
                    onDragEnd={() => setDraggedIndex(null)}
                  />
                  <Button
                    type="text"
                    aria-label={t('log.extractor.moveUp')}
                    icon={<ArrowUpOutlined />}
                    disabled={actionLoading || !instance?.canOperate || index === 0}
                    onClick={() => void move(index, -1)}
                  />
                  <Button
                    type="text"
                    aria-label={t('log.extractor.moveDown')}
                    icon={<ArrowDownOutlined />}
                    disabled={
                      actionLoading ||
                      !instance?.canOperate ||
                      index === rules.length - 1
                    }
                    onClick={() => void move(index, 1)}
                  />
                  <Button type="link" onClick={() => openEditor(rule)}>
                    {instance?.canOperate ? t('common.edit') : t('common.view')}
                  </Button>
                  {instance?.canOperate && (
                    <Popconfirm
                      title={t('common.deleteTitle')}
                      okButtonProps={{ loading: actionLoading }}
                      onConfirm={() => void remove(rule)}
                    >
                      <Button type="link" danger icon={<DeleteOutlined />}>
                        {t('common.delete')}
                      </Button>
                    </Popconfirm>
                  )}
                </Space>
              )
            }
          ]}
        />
      </Drawer>

      <Modal
        width="min(820px, calc(100vw - 32px))"
        title={editing ? t('log.extractor.edit') : t('log.extractor.add')}
        open={editorOpen}
        confirmLoading={saving}
        okButtonProps={{ disabled: !instance?.canOperate }}
        onOk={() => void save()}
        onCancel={() => setEditorOpen(false)}
        destroyOnHidden
        styles={{ body: { maxHeight: 'calc(100vh - 220px)', overflowY: 'auto' } }}
      >
        <Form<FormValue>
          form={form}
          layout="vertical"
          disabled={!instance?.canOperate}
        >
          <div className="grid grid-cols-2 gap-x-[16px]">
            <Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item
              name="extractor_type"
              label={t('common.type')}
              rules={[{ required: true }]}
            >
              <Select options={EXTRACTOR_TYPES.map((value) => ({ value, label: value }))} />
            </Form.Item>
            <Form.Item
              name="source_field"
              label={t('log.extractor.sourceField')}
              extra={t('log.extractor.pathSyntaxHint')}
              rules={[{ required: true }]}
            >
              <AutoComplete options={fieldOptions} placeholder={t('log.extractor.pathPlaceholder')} />
            </Form.Item>
            {!['kv', 'regex'].includes(extractorType || '') && (
              <Form.Item
                name="target_field"
                label={t('log.extractor.targetField')}
                rules={[
                  {
                    required: ['copy', 'split'].includes(extractorType || '')
                  }
                ]}
              >
                <AutoComplete options={fieldOptions} placeholder={t('log.extractor.pathPlaceholder')} />
              </Form.Item>
            )}
          </div>
          <Form.Item name="delete_source" valuePropName="checked">
            <Checkbox>{t('log.extractor.deleteSource')}</Checkbox>
          </Form.Item>
          <Form.Item label={t('log.extractor.condition')}>
            <Form.Item name="condition_mode" noStyle>
              <Select
                className="mb-[8px] w-[120px]"
                options={['AND', 'OR'].map((value) => ({ value, label: value }))}
              />
            </Form.Item>
            <Form.List name="conditions">
              {(fields, { add, remove: removeCondition }) => (
                <div className="w-full">
                  {fields.map(({ key, name }) => (
                    <Row gutter={8} align="top" key={key}>
                      <Col xs={24} md={8}>
                        <Form.Item
                          name={[name, 'field']}
                          rules={[{ required: true }]}
                        >
                          <AutoComplete
                            className="w-full"
                            options={fieldOptions}
                            placeholder={t('log.extractor.conditionField')}
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} md={5}>
                        <Form.Item name={[name, 'op']} rules={[{ required: true }]}>
                          <Select
                            className="w-full"
                            options={OPERATORS.map((value) => ({ value, label: value }))}
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} md={8}>
                        <Form.Item name={[name, 'value']}>
                          <Input placeholder={t('log.extractor.conditionValue')} />
                        </Form.Item>
                      </Col>
                      <Col xs={24} md={3}>
                        <Button danger type="text" onClick={() => removeCondition(name)}>
                          {t('common.delete')}
                        </Button>
                      </Col>
                    </Row>
                  ))}
                  <Button type="dashed" onClick={() => add({ op: '==' })}>
                    {t('log.extractor.addCondition')}
                  </Button>
                </div>
              )}
            </Form.List>
          </Form.Item>
          {extractorType === 'split' && (
            <div className="grid grid-cols-2 gap-x-[16px]">
              <Form.Item
                name="delimiter"
                label={t('log.extractor.delimiter')}
                rules={[{ required: true }]}
              >
                <Input />
              </Form.Item>
              <Form.Item
                name="index"
                label={t('log.extractor.index')}
                rules={[{ required: true, type: 'number', min: 0 }]}
              >
                <InputNumber className="w-full" min={0} precision={0} />
              </Form.Item>
            </div>
          )}
          {extractorType === 'kv' && (
            <>
              <div className="grid grid-cols-2 gap-x-[16px]">
                <Form.Item
                  name="key_value_delimiter"
                  label={t('log.extractor.keyValueDelimiter')}
                  rules={[{ required: true }]}
                >
                  <Input />
                </Form.Item>
                <Form.Item
                  name="field_delimiter"
                  label={t('log.extractor.fieldDelimiter')}
                  rules={[{ required: true }]}
                >
                  <Input />
                </Form.Item>
              </div>
              <Form.Item
                name="field_mapping_text"
                label={t('log.extractor.fieldMapping')}
              >
                <Input.TextArea rows={3} />
              </Form.Item>
            </>
          )}
          {['regex', 'regex_replace'].includes(extractorType || '') && (
            <Form.Item
              name="pattern"
              label={t('log.extractor.pattern')}
              rules={[{ required: true }]}
            >
              <Input />
            </Form.Item>
          )}
          {extractorType === 'regex' && (
            <Form.Item
              name="group_mapping_text"
              label={t('log.extractor.groupMapping')}
            >
              <Input.TextArea rows={3} />
            </Form.Item>
          )}
          {extractorType === 'regex_replace' && (
            <Form.Item
              name="replacement"
              label={t('log.extractor.replacement')}
            >
              <Input />
            </Form.Item>
          )}
          <Typography.Title level={5}>{t('log.extractor.preview')}</Typography.Title>
          {samplesError && (
            <Alert
              className="mb-[8px]"
              type="warning"
              showIcon
              message={t('log.extractor.samplesError')}
              action={
                <Button
                  size="small"
                  loading={samplesLoading}
                  onClick={() => void loadSamples().catch(() => undefined)}
                >
                  {t('common.retry')}
                </Button>
              }
            />
          )}
          <Space.Compact className="w-full">
            <Select
              className="w-full"
              value={sampleIndex}
              placeholder={t('log.extractor.selectSample')}
              options={samples.map((sample, index) => ({
                value: index,
                label: JSON.stringify(sample).slice(0, 160)
              }))}
              onChange={setSampleIndex}
              disabled={false}
            />
            <Button
              loading={samplesLoading}
              disabled={false}
              onClick={() => void loadSamples().catch(() => undefined)}
            >
              {t('log.extractor.loadSamples')}
            </Button>
            <Button
              type="primary"
              disabled={sampleIndex === null}
              onClick={() => void runPreview()}
            >
              {t('log.extractor.runPreview')}
            </Button>
          </Space.Compact>
          {preview && (
            <Input.TextArea
              className="mt-[8px] font-mono"
              rows={8}
              readOnly
              value={JSON.stringify(preview, null, 2)}
              aria-label={t('log.extractor.previewResult')}
            />
          )}
        </Form>
      </Modal>
    </>
  );
};

export default LogExtractorDrawer;
