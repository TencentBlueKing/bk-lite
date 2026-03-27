'use client';

import React, { forwardRef, useImperativeHandle, useMemo, useState } from 'react'
import { Alert, Button, Form, Modal, Select, Tag } from 'antd'
import type { ModelUniqueRuleItem, UniqueRuleFieldMeta } from '@/app/cmdb/types/assetManage'
import { useTranslation } from '@/utils/i18n'

interface UniqueRuleModalConfig {
  mode: 'create' | 'edit'
  rule?: ModelUniqueRuleItem
  candidateFields: UniqueRuleFieldMeta[]
}

export interface UniqueRuleModalRef {
  showModal: (config: UniqueRuleModalConfig) => void
}

interface Props {
  onSubmit: (fieldIds: string[], ruleId?: string) => Promise<void>
}

const UniqueRuleModal = forwardRef<UniqueRuleModalRef, Props>(({ onSubmit }, ref) => {
  const { t } = useTranslation()
  const [form] = Form.useForm()
  const [visible, setVisible] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [mode, setMode] = useState<'create' | 'edit'>('create')
  const [rule, setRule] = useState<ModelUniqueRuleItem | undefined>()
  const [candidateFields, setCandidateFields] = useState<UniqueRuleFieldMeta[]>([])

  useImperativeHandle(ref, () => ({
    showModal: (config) => {
      setMode(config.mode)
      setRule(config.rule)
      setCandidateFields(config.candidateFields)
      setVisible(true)
      form.setFieldsValue({ field_ids: config.rule?.field_ids || [] })
    },
  }))

  const options = useMemo(() => {
    return candidateFields.filter((field) => field.selectable).map((field) => ({
      label: field.attr_name,
      value: field.attr_id,
    }))
  }, [candidateFields])

  const disabledFields = useMemo(() => {
    return candidateFields.filter((field) => !field.selectable)
  }, [candidateFields])

  const handleOk = async () => {
    const values = await form.validateFields()
    setSubmitting(true)
    try {
      await onSubmit(values.field_ids, rule?.rule_id)
      setVisible(false)
      form.resetFields()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={visible}
      title={mode === 'create' ? t('Model.addUniqueRule') : t('Model.editUniqueRule')}
      onCancel={() => setVisible(false)}
      footer={[
        <Button key="cancel" onClick={() => setVisible(false)}>{t('common.cancel')}</Button>,
        <Button key="ok" type="primary" loading={submitting} onClick={handleOk}>{t('common.confirm')}</Button>,
      ]}
    >
      <Form form={form} layout="vertical">
        {options.length === 0 && (
          <Alert
            className="mb-4"
            type="warning"
            showIcon
            message={t('Model.noEligibleUniqueFields')}
            description={t('Model.noEligibleUniqueFieldsDesc')}
          />
        )}
        <Form.Item
          label={t('Model.uniqueRuleFields')}
          name="field_ids"
          rules={[{ required: true, message: t('required') }]}
        >
          <Select
            mode="multiple"
            options={options}
            placeholder={t('common.selectMsg')}
            disabled={options.length === 0}
          />
        </Form.Item>
        {disabledFields.length > 0 && (
          <div>
            <div className="mb-2 text-[var(--color-text-2)]">
              {t('Model.unavailableUniqueFields')}
            </div>
            <div className="flex flex-wrap gap-2">
              {disabledFields.map((field) => (
                <Tag key={field.attr_id} color="default">
                  {field.attr_name}
                  {field.disabled_reason ? `（${field.disabled_reason}）` : ''}
                </Tag>
              ))}
            </div>
          </div>
        )}
      </Form>
    </Modal>
  )
})

UniqueRuleModal.displayName = 'UniqueRuleModal'

export default UniqueRuleModal
