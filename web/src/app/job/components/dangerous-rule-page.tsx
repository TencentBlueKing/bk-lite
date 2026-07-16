'use client';

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Button, Input, Select, Switch, Tag, Modal, message, Form, Radio } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import { DangerousRule, DangerousRuleFormData, DangerousRuleListResponse, DangerousRuleMatchType, DangerousRuleParams } from '@/app/job/types';
import { ColumnItem } from '@/types';
import GroupTreeSelect from '@/components/group-tree-select';
import SearchCombination from '@/components/search-combination';
import { SearchFilters, FieldConfig } from '@/components/search-combination/types';
import { AxiosRequestConfig } from 'axios';

interface DangerousRuleApiMethods {
  getList: (params?: DangerousRuleParams, config?: AxiosRequestConfig) => Promise<DangerousRuleListResponse>;
  create: (data: DangerousRuleFormData) => Promise<DangerousRule>;
  update: (id: number, data: Partial<DangerousRuleFormData>) => Promise<DangerousRule>;
  patch: (id: number, data: Partial<DangerousRule>) => Promise<DangerousRule>;
  remove: (id: number) => Promise<void>;
}

interface DangerousRulePageProps {
  title: string;
  description: string;
  addModalTitle: string;
  editModalTitle: string;
  patternLabel: string;
  patternPlaceholder: string;
  patternHelp: string;
  patternExamples: string[];
  forbiddenLabel: string;
  confirmLabel: string;
  strategyHelp: string;
  ruleNamePlaceholder: string;
  matchTypeLabel?: string;
  matchTypeOptions?: Array<{
    label: string;
    value: DangerousRuleMatchType;
    help: string;
    placeholder: string;
    examples: string[];
  }>;
  api: DangerousRuleApiMethods;
}

const DangerousRulePage: React.FC<DangerousRulePageProps> = ({
  title,
  description,
  addModalTitle,
  editModalTitle,
  patternLabel,
  patternPlaceholder,
  patternHelp,
  patternExamples,
  forbiddenLabel,
  confirmLabel,
  strategyHelp,
  ruleNamePlaceholder,
  matchTypeLabel,
  matchTypeOptions,
  api,
}) => {
  const { t } = useTranslation();
  const { isLoading: isApiReady } = useApiClient();

  const [form] = Form.useForm();
  const [data, setData] = useState<DangerousRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchFilters, setSearchFilters] = useState<SearchFilters>({});
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const [modalOpen, setModalOpen] = useState(false);
  const [modalType, setModalType] = useState<'add' | 'edit'>('add');
  const [editingRule, setEditingRule] = useState<DangerousRule | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [togglingIds, setTogglingIds] = useState<Set<number>>(new Set());
  const currentMatchType = Form.useWatch('match_type', form) as DangerousRuleMatchType | undefined;

  const selectedMatchTypeOption = useMemo(() => {
    if (!matchTypeOptions?.length) return null;
    return matchTypeOptions.find(option => option.value === currentMatchType) || matchTypeOptions[0];
  }, [currentMatchType, matchTypeOptions]);

  const resolvedPatternPlaceholder = selectedMatchTypeOption?.placeholder || patternPlaceholder;
  const resolvedPatternHelp = selectedMatchTypeOption?.help || patternHelp;
  const resolvedPatternExamples = selectedMatchTypeOption?.examples || patternExamples;
  const matchTypeLabelMap = useMemo(() => {
    return new Map((matchTypeOptions || []).map(option => [option.value, option.label]));
  }, [matchTypeOptions]);

  const fetchData = useCallback(
    async (params: { filters?: SearchFilters; current?: number; pageSize?: number } = {}) => {
      setLoading(true);
      try {
        const filters = params.filters ?? searchFilters;
        const queryParams: Record<string, unknown> = {
          page: params.current ?? pagination.current,
          page_size: params.pageSize ?? pagination.pageSize,
        };
        // Convert SearchFilters to flat query params
        if (filters && Object.keys(filters).length > 0) {
          Object.entries(filters).forEach(([field, conditions]) => {
            conditions.forEach((condition) => {
              if (field === 'is_enabled') {
                queryParams.is_enabled = condition.value;
              } else if (condition.lookup_expr === 'in' && Array.isArray(condition.value)) {
                queryParams[field] = (condition.value as string[]).join(',');
              } else {
                queryParams[field] = condition.value;
              }
            });
          });
        }
        const res = await api.getList(queryParams as any);
        setData(res.items || []);
        setPagination((prev) => ({
          ...prev,
          total: res.count || 0,
        }));
      } finally {
        setLoading(false);
      }
    },
    [searchFilters, pagination.current, pagination.pageSize, api]
  );

  useEffect(() => {
    if (!isApiReady) {
      fetchData();
    }
  }, [isApiReady]);

  useEffect(() => {
    if (!isApiReady) {
      fetchData();
    }
  }, [pagination.current, pagination.pageSize]);

  const handleSearchChange = useCallback((filters: SearchFilters) => {
    setSearchFilters(filters);
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchData({ filters, current: 1 });
  }, [fetchData]);

  const fieldConfigs: FieldConfig[] = useMemo(() => [
    {
      name: 'name',
      label: t('job.ruleName'),
      lookup_expr: 'icontains',
    },
    {
      name: 'pattern',
      label: patternLabel,
      lookup_expr: 'icontains',
    },
    {
      name: 'level',
      label: t('job.handleStrategy'),
      lookup_expr: 'in',
      options: [
        { id: 'forbidden', name: forbiddenLabel },
        { id: 'confirm', name: confirmLabel },
      ],
    },
    ...(matchTypeOptions?.length ? [{
      name: 'match_type',
      label: matchTypeLabel || t('job.matchType'),
      lookup_expr: 'in',
      options: matchTypeOptions.map(option => ({ id: option.value, name: option.label })),
    } satisfies FieldConfig] : []),
    {
      name: 'is_enabled',
      label: t('job.enableStatus'),
      lookup_expr: 'bool',
      options: [
        { id: 'true', name: t('common.yes') },
        { id: 'false', name: t('common.no') },
      ],
    },
  ], [confirmLabel, forbiddenLabel, matchTypeLabel, matchTypeOptions, patternLabel, t]);

  const handleTableChange = (pag: any) => {
    setPagination(pag);
  };

  const handleToggleEnabled = async (record: DangerousRule) => {
    setTogglingIds((prev) => new Set(prev).add(record.id));
    try {
      await api.patch(record.id, {
        is_enabled: !record.is_enabled,
      });
      message.success(
        record.is_enabled ? t('job.ruleDisabled') : t('job.ruleEnabled')
      );
      fetchData();
    } catch {
      // error handled by interceptor
    } finally {
      setTogglingIds((prev) => {
        const next = new Set(prev);
        next.delete(record.id);
        return next;
      });
    }
  };

  const handleDelete = (record: DangerousRule) => {
    Modal.confirm({
      title: t('job.deleteRule'),
      content: t('job.deleteRuleConfirm'),
      okText: t('job.confirm'),
      cancelText: t('job.cancel'),
      centered: true,
      onOk: async () => {
        await api.remove(record.id);
        message.success(t('job.deleteRule'));
        fetchData();
      },
    });
  };

  const openAddModal = () => {
    setModalType('add');
    setEditingRule(null);
    form.resetFields();
    form.setFieldsValue({
      level: 'forbidden',
      ...(matchTypeOptions?.length ? { match_type: matchTypeOptions[0].value } : {}),
    });
    setModalOpen(true);
  };

  const openEditModal = (record: DangerousRule) => {
    setModalType('edit');
    setEditingRule(record);
    form.resetFields();
    form.setFieldsValue({
      name: record.name,
      pattern: record.pattern,
      match_type: record.match_type || matchTypeOptions?.[0]?.value,
      level: record.level,
      description: record.description,
      team: record.team || [],
    });
    setModalOpen(true);
  };

  const handleSubmit = async (enableAfterSave: boolean) => {
    try {
      const values = await form.validateFields();
      setConfirmLoading(true);
      const formData: DangerousRuleFormData = {
        ...values,
        is_enabled: enableAfterSave,
      };

      if (modalType === 'add') {
        await api.create(formData);
        message.success(t('job.addRule'));
      } else if (editingRule) {
        await api.update(editingRule.id, formData);
        message.success(t('job.editRule'));
      }
      setModalOpen(false);
      fetchData();
    } catch {
      // validation or API error
    } finally {
      setConfirmLoading(false);
    }
  };

  const columns: ColumnItem[] = [
    {
      title: t('job.ruleName'),
      dataIndex: 'name',
      key: 'name',
      width: 160,
    },
    {
      title: patternLabel,
      dataIndex: 'pattern',
      key: 'pattern',
      width: 240,
      render: (_: unknown, record: DangerousRule) => (
        <code
          className="px-2 py-0.5 rounded text-xs"
          style={{
            color: '#d46b08',
            backgroundColor: 'rgba(250, 173, 20, 0.1)',
            border: '1px solid rgba(250, 173, 20, 0.3)',
          }}
        >
          {record.pattern}
        </code>
      ),
    },
    ...(matchTypeOptions?.length ? [{
      title: matchTypeLabel || t('job.matchType'),
      dataIndex: 'match_type',
      key: 'match_type',
      width: 120,
      render: (_: unknown, record: DangerousRule) => (
        <span>{matchTypeLabelMap.get(record.match_type || matchTypeOptions[0].value) || '-'}</span>
      ),
    } satisfies ColumnItem] : []),
    {
      title: t('job.handleStrategy'),
      dataIndex: 'level',
      key: 'level',
      width: 120,
      render: (_: unknown, record: DangerousRule) => {
        const isForbidden = record.level === 'forbidden';
        return (
          <Tag
            color={isForbidden ? 'error' : 'processing'}
            style={{ margin: 0 }}
          >
            {isForbidden ? forbiddenLabel : confirmLabel}
          </Tag>
        );
      },
    },
    {
      title: t('job.enableStatus'),
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      width: 100,
      render: (_: unknown, record: DangerousRule) => (
        <Switch
          size="small"
          checked={record.is_enabled}
          loading={togglingIds.has(record.id)}
          disabled={togglingIds.has(record.id)}
          onChange={() => handleToggleEnabled(record)}
        />
      ),
    },
    {
      title: t('job.updateTime'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (_: unknown, record: DangerousRule) => {
        if (!record.updated_at) return <span>-</span>;
        const d = new Date(record.updated_at);
        const pad = (n: number) => String(n).padStart(2, '0');
        return <span>{`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`}</span>;
      },
    },
    {
      title: t('job.operation'),
      dataIndex: 'action',
      key: 'action',
      width: 120,
      render: (_: unknown, record: DangerousRule) => (
        <div className="flex items-center gap-3">
          <a
            className="text-(--color-primary) cursor-pointer"
            onClick={() => openEditModal(record)}
          >
            {t('job.editRule')}
          </a>
          <a
            className="text-(--color-primary) cursor-pointer"
            onClick={() => handleDelete(record)}
          >
            {t('job.deleteRule')}
          </a>
        </div>
      ),
    },
  ];

  return (
    <div className="w-full h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div
        className="rounded-lg px-6 py-4 mb-4 shrink-0"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        <h2
          className="text-base font-medium m-0 mb-1"
          style={{ color: 'var(--color-text-1)' }}
        >
          {title}
        </h2>
        <p className="text-sm m-0" style={{ color: 'var(--color-text-3)' }}>
          {description}
        </p>
      </div>

      {/* Table Section */}
      <div
        className="rounded-lg px-6 py-6 flex-1 flex flex-col overflow-hidden"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        {/* Toolbar */}
        <div className="flex justify-between mb-4 shrink-0">
          <SearchCombination
            fieldConfigs={fieldConfigs}
            onChange={handleSearchChange}
            fieldWidth={120}
            selectWidth={300}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={openAddModal}
          >
            {t('job.addRule')}
          </Button>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-hidden">
          <CustomTable
            columns={columns}
            dataSource={data}
            loading={loading}
            rowKey="id"
            pagination={pagination}
            onChange={handleTableChange}
          />
        </div>
      </div>

      {/* Add/Edit Modal */}
      <OperateModal
        title={modalType === 'add' ? addModalTitle : editModalTitle}
        open={modalOpen}
        confirmLoading={confirmLoading}
        onCancel={() => setModalOpen(false)}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={() => setModalOpen(false)}>{t('job.cancel')}</Button>
            <Button loading={confirmLoading} onClick={() => handleSubmit(false)}>{t('job.saveOnly')}</Button>
            <Button type="primary" loading={confirmLoading} onClick={() => handleSubmit(true)}>{t('job.saveAndEnable')}</Button>
          </div>
        }
        width={680}
      >
        <Form form={form} layout="vertical" colon={false}>
          <Form.Item
            name="name"
            label={t('job.ruleName')}
            rules={[{ required: true, message: ruleNamePlaceholder }]}
          >
            <Input placeholder={ruleNamePlaceholder} />
          </Form.Item>

          {matchTypeOptions?.length ? (
            <Form.Item
              name="match_type"
              label={matchTypeLabel || t('job.matchType')}
              rules={[{ required: true, message: t('job.matchTypePlaceholder') }]}
            >
              <Radio.Group>
                {matchTypeOptions.map(option => (
                  <Radio key={option.value} value={option.value}>{option.label}</Radio>
                ))}
              </Radio.Group>
            </Form.Item>
          ) : null}

          <Form.Item
            name="pattern"
            label={patternLabel}
            rules={[
              {
                required: true,
                message: resolvedPatternPlaceholder,
              },
            ]}
          >
            <Input placeholder={resolvedPatternPlaceholder} />
          </Form.Item>
          <div className="text-xs mb-2" style={{ color: 'var(--color-text-3)', marginTop: -16 }}>
            {resolvedPatternHelp}
          </div>
          <div
            className="rounded-md px-4 py-3 mb-6 text-xs leading-relaxed bg-[#f5f7fa]"
            style={{ color: 'var(--color-text-2)' }}
          >
            <div className="font-medium mb-1">{t('job.matchPatternExamplesTitle')}</div>
            <ul className="list-disc pl-4 m-0 space-y-0.5">
              {resolvedPatternExamples.map((example, index) => (
                <li key={index}>{example}</li>
              ))}
            </ul>
          </div>

          <Form.Item
            name="level"
            label={t('job.handleStrategy')}
            rules={[{ required: true }]}
          >
            <Select
              options={[
                { label: forbiddenLabel, value: 'forbidden' },
                { label: confirmLabel, value: 'confirm' },
              ]}
            />
          </Form.Item>
          <div
            className="text-xs mb-6 whitespace-pre-line"
            style={{ color: 'var(--color-text-3)', marginTop: -16 }}
          >
            {strategyHelp}
          </div>

          <Form.Item
            name="team"
            label={t('job.organization')}
            rules={[{ required: true, message: t('job.organizationPlaceholder') }]}
          >
            <GroupTreeSelect multiple placeholder={t('job.organizationPlaceholder')} />
          </Form.Item>

          <Form.Item name="description" label={t('job.description')}>
            <Input.TextArea
              rows={3}
              placeholder={t('job.descriptionPlaceholder')}
            />
          </Form.Item>
        </Form>
      </OperateModal>
    </div>
  );
};

export default DangerousRulePage;
