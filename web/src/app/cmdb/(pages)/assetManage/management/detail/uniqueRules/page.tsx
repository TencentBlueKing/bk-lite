'use client';

import React, { useEffect, useRef, useState } from 'react'
import { Alert, Button, Modal, Space, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import CustomTable from '@/components/custom-table'
import PermissionWrapper from '@/components/permission'
import { useTranslation } from '@/utils/i18n'
import { useModelApi } from '@/app/cmdb/api'
import { useModelDetail } from '../context'
import type { ModelUniqueRuleItem, UniqueRuleFieldMeta, UniqueRuleListResponse } from '@/app/cmdb/types/assetManage'
import UniqueRuleModal, { UniqueRuleModalRef } from './uniqueRuleModal'

const UniqueRulesPage: React.FC = () => {
  const { t } = useTranslation()
  const { confirm } = Modal
  const modalRef = useRef<UniqueRuleModalRef>(null)
  const modelDetail = useModelDetail()
  const modelId = modelDetail?.model_id
  const modelPermission = modelDetail?.permission || []
  const {
    getModelUniqueRules,
    createModelUniqueRule,
    updateModelUniqueRule,
    deleteModelUniqueRule,
  } = useModelApi()

  const [loading, setLoading] = useState(false)
  const [rules, setRules] = useState<ModelUniqueRuleItem[]>([])
  const [candidateFields, setCandidateFields] = useState<UniqueRuleFieldMeta[]>([])

  const loadData = async (editingRuleId?: string) => {
    if (!modelId) return
    setLoading(true)
    try {
      const data = await getModelUniqueRules(modelId, editingRuleId) as UniqueRuleListResponse
      setRules(data.rules || [])
      setCandidateFields(data.candidate_fields || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [modelId])

  const openCreateModal = async () => {
    if (!modelId) return
    const data = await getModelUniqueRules(modelId) as UniqueRuleListResponse
    modalRef.current?.showModal({
      mode: 'create',
      candidateFields: data.candidate_fields || [],
    })
  }

  const columns: ColumnsType<ModelUniqueRuleItem> = [
    {
      title: t('Model.uniqueRuleFields'),
      dataIndex: 'field_names',
      key: 'field_names',
      render: (_, record) => record.field_names.join(' + '),
    },
    {
      title: t('action'),
      key: 'action',
      width: 180,
      render: (_, record) => (
        <Space>
          <PermissionWrapper requiredPermissions={['Edit Model']} instPermissions={modelPermission}>
            <Button
              type="link"
              onClick={async () => {
                const data = await getModelUniqueRules(modelId!, record.rule_id) as UniqueRuleListResponse
                modalRef.current?.showModal({
                  mode: 'edit',
                  rule: record,
                  candidateFields: data.candidate_fields || [],
                })
              }}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Edit Model']} instPermissions={modelPermission}>
            <Button
              type="link"
              danger
              onClick={() => {
                confirm({
                  title: t('common.delConfirm'),
                  content: t('common.delConfirmCxt'),
                  onOk: async () => {
                    await deleteModelUniqueRule(modelId!, record.rule_id)
                    message.success(t('successfullyDeleted'))
                    await loadData()
                  },
                })
              }}
            >
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="flex justify-end mb-[16px]">
        <PermissionWrapper requiredPermissions={['Edit Model']} instPermissions={modelPermission}>
          <Button
            type="primary"
            disabled={rules.length >= 3}
            onClick={openCreateModal}
          >
            {t('Model.addUniqueRule')}
          </Button>
        </PermissionWrapper>
      </div>
      {candidateFields.length === 0 && (
        <Alert
          className="mb-[16px]"
          type="info"
          showIcon
          message={t('Model.noEligibleUniqueFields')}
          description={t('Model.noEligibleUniqueFieldsDesc')}
        />
      )}
      <CustomTable
        size="middle"
        columns={columns}
        dataSource={rules}
        loading={loading}
        rowKey="rule_id"
        pagination={false}
      />
      <UniqueRuleModal
        ref={modalRef}
        onSubmit={async (fieldIds, ruleId) => {
          if (!modelId) return
          if (ruleId) {
            await updateModelUniqueRule(modelId, ruleId, { field_ids: fieldIds })
            message.success(t('successfullyModified'))
          } else {
            await createModelUniqueRule(modelId, { field_ids: fieldIds })
            message.success(t('successfullyAdded'))
          }
          await loadData()
        }}
      />
    </div>
  )
}

export default UniqueRulesPage
