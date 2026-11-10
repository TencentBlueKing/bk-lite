'use client';

import React, { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Alert, Button, Modal, Space, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import { useTranslation } from '@/utils/i18n';
import { useModelApi } from '@/app/cmdb/api';
import { useModelDetail } from '../context';
import DuplicateRuleModal, { DuplicateRuleItem, DuplicateRuleModalRef } from './duplicateRuleModal';

const DuplicateRulesPage: React.FC = () => {
  const { t } = useTranslation();
  const { confirm } = Modal;
  const modalRef = useRef<DuplicateRuleModalRef>(null);
  const modelDetail = useModelDetail();
  const modelId = modelDetail?.model_id;
  const modelPermission = modelDetail?.permission || [];
  const {
    getModelDuplicateRules,
    createModelDuplicateRule,
    updateModelDuplicateRule,
    deleteModelDuplicateRule,
  } = useModelApi();
  const [loading, setLoading] = useState(false);
  const [rules, setRules] = useState<DuplicateRuleItem[]>([]);

  const loadData = async () => {
    if (!modelId) return;
    setLoading(true);
    try {
      const data = await getModelDuplicateRules(modelId);
      setRules(data.rules || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [modelId]);

  const openCreateModal = async () => {
    if (!modelId) return;
    const data = await getModelDuplicateRules(modelId);
    modalRef.current?.showModal({ mode: 'create', candidateFields: data.candidate_fields || [] });
  };

  const handleSubmit = async (fieldIds: string[], ruleId?: string) => {
    if (!modelId) return;
    if (ruleId) {
      await updateModelDuplicateRule(modelId, ruleId, { field_ids: fieldIds });
      message.success(t('successfullyModified'));
    } else {
      await createModelDuplicateRule(modelId, { field_ids: fieldIds });
      message.success(t('successfullyAdded'));
    }
    await loadData();
  };

  const columns: ColumnsType<DuplicateRuleItem> = [
    {
      title: t('Model.uniqueRuleFields'),
      dataIndex: 'field_names',
      render: (_, record) => (
        <span className="font-medium text-[var(--color-text-1)]">{record.field_names.join(' + ')}</span>
      ),
    },
    {
      title: t('type'),
      dataIndex: 'rule_type',
      width: 120,
      render: (_, record) => (record.rule_type === 'joint' ? t('Governance.jointField') : t('Governance.singleField')),
    },
    {
      title: t('Governance.duplicate'),
      dataIndex: 'problem_group_count',
      width: 120,
      render: (_, record) => (
        <Link href={`/cmdb/assetManage/governance?path=duplicate&model_id=${modelId}&rule_id=${record.rule_id}`}>
          {t('Governance.problemGroups', undefined, { count: record.problem_group_count || 0 })}
        </Link>
      ),
    },
    {
      title: t('common.action'),
      key: 'action',
      width: 140,
      render: (_, record) => (
        <Space>
          <PermissionWrapper requiredPermissions={['Edit Model']} instPermissions={modelPermission}>
            <Button
              type="link"
              onClick={async () => {
                const data = await getModelDuplicateRules(modelId!);
                modalRef.current?.showModal({
                  mode: 'edit',
                  rule: record,
                  candidateFields: data.candidate_fields || [],
                });
              }}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Edit Model']} instPermissions={modelPermission}>
            <Button
              type="link"
              danger
              onClick={() => confirm({
                title: t('common.delConfirm'),
                content: t('common.delConfirmCxt'),
                okButtonProps: { danger: true },
                onOk: async () => {
                  await deleteModelDuplicateRule(modelId!, record.rule_id);
                  message.success(t('successfullyDeleted'));
                  await loadData();
                },
              })}
            >
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        </Space>
      ),
    },
  ];

  return (
    <div className="min-w-0 w-full">
      <Alert className="mb-4" type="info" showIcon message={t('Governance.duplicateTip')} />
      <div className="mb-4 flex justify-end">
        <PermissionWrapper requiredPermissions={['Edit Model']} instPermissions={modelPermission}>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
            {t('Model.addUniqueRule')}
          </Button>
        </PermissionWrapper>
      </div>
      <CustomTable
        rowKey="rule_id"
        loading={loading}
        columns={columns}
        dataSource={rules}
        pagination={false}
      />
      <DuplicateRuleModal ref={modalRef} onSubmit={handleSubmit} />
    </div>
  );
};

export default DuplicateRulesPage;
