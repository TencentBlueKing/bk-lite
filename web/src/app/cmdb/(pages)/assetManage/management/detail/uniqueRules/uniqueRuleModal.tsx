'use client';

import React, { forwardRef, useImperativeHandle, useMemo, useState } from 'react'
import { Button, Form, Modal, Select } from 'antd';
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
  const horizontalLayout = {
    labelCol: { flex: '84px' },
    wrapperCol: { flex: 1 },
  };

  useImperativeHandle(ref, () => ({
    showModal: (config) => {
      setMode(config.mode)
      setRule(config.rule)
      setCandidateFields(config.candidateFields)
      setVisible(true)
      form.setFieldsValue({
        field_ids: config.rule?.field_ids || [],
      });
    },
  }))

  const options = useMemo(() => {
    return [...candidateFields]
      .sort((a, b) => Number(b.selectable) - Number(a.selectable))
      .map((field) => ({
        label: field.selectable
          ? field.attr_name
          : `${field.attr_name}（${field.disabled_reason || t('Model.fieldUnavailable')}）`,
        value: field.attr_id,
        disabled: !field.selectable,
      }));
  }, [candidateFields, t]);

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
      title={
        mode === 'create' ? t('Model.addUniqueRule') : t('Model.editUniqueRule')
      }
      onCancel={() => setVisible(false)}
      maskClosable={false}
      centered
      footer={[
        <Button key="cancel" onClick={() => setVisible(false)}>
          {t('common.cancel')}
        </Button>,
        <Button key="ok" type="primary" loading={submitting} onClick={handleOk}>
          {t('common.confirm')}
        </Button>,
      ]}
    >
      <Form form={form} layout="vertical" className="mt-4">
        <Form.Item
          label={t('Model.uniqueRuleFields')}
          name="field_ids"
          rules={[{ required: true, message: t('required') }]}
          layout="horizontal"
          {...horizontalLayout}
        >
          <Select
            mode="multiple"
            options={options}
            placeholder={t('common.selectMsg')}
            showSearch
            optionFilterProp="label"
            filterOption={(input, option) =>
              String(option?.label || '')
                .toLowerCase()
                .includes(input.toLowerCase())
            }
          />
        </Form.Item>
      </Form>
    </Modal>
  );
})

UniqueRuleModal.displayName = 'UniqueRuleModal'

export default UniqueRuleModal
