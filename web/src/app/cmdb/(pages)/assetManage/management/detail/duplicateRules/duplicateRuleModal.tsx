'use client';

import React, { forwardRef, useImperativeHandle, useMemo, useState } from 'react';
import { Button, Form, Modal, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';

export interface DuplicateRuleField {
  attr_id: string;
  attr_name: string;
  selectable: boolean;
  disabled_reason: string;
}

export interface DuplicateRuleItem {
  rule_id: string;
  field_ids: string[];
  field_names: string[];
  rule_type: 'single' | 'joint';
  problem_group_count: number;
}

interface ModalConfig {
  mode: 'create' | 'edit';
  rule?: DuplicateRuleItem;
  candidateFields: DuplicateRuleField[];
}

export interface DuplicateRuleModalRef {
  showModal: (config: ModalConfig) => void;
}

interface Props {
  onSubmit: (fieldIds: string[], ruleId?: string) => Promise<void>;
}

const DuplicateRuleModal = forwardRef<DuplicateRuleModalRef, Props>(({ onSubmit }, ref) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [visible, setVisible] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [mode, setMode] = useState<'create' | 'edit'>('create');
  const [rule, setRule] = useState<DuplicateRuleItem | undefined>();
  const [candidateFields, setCandidateFields] = useState<DuplicateRuleField[]>([]);

  useImperativeHandle(ref, () => ({
    showModal: (config) => {
      setMode(config.mode);
      setRule(config.rule);
      setCandidateFields(config.candidateFields);
      setVisible(true);
      form.setFieldsValue({ field_ids: config.rule?.field_ids || [] });
    },
  }));

  const options = useMemo(() => (
    [...candidateFields]
      .sort((left, right) => Number(right.selectable) - Number(left.selectable))
      .map((field) => ({
        label: field.selectable ? field.attr_name : `${field.attr_name}（${field.disabled_reason || t('Model.fieldUnavailable')}）`,
        value: field.attr_id,
        disabled: !field.selectable,
      }))
  ), [candidateFields, t]);

  const handleOk = async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      await onSubmit(values.field_ids, rule?.rule_id);
      setVisible(false);
      form.resetFields();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={visible}
      title={mode === 'create' ? t('Model.addUniqueRule') : t('Model.editUniqueRule')}
      onCancel={() => setVisible(false)}
      maskClosable={false}
      centered
      footer={[
        <Button key="cancel" onClick={() => setVisible(false)}>{t('common.cancel')}</Button>,
        <Button key="ok" type="primary" loading={submitting} onClick={handleOk}>{t('common.confirm')}</Button>,
      ]}
    >
      <Form form={form} layout="vertical" className="mt-4">
        <Form.Item label={t('Model.uniqueRuleFields')} name="field_ids" rules={[{ required: true, message: t('required') }]}>
          <Select mode="multiple" options={options} placeholder={t('common.selectMsg')} showSearch optionFilterProp="label" />
        </Form.Item>
      </Form>
    </Modal>
  );
});

DuplicateRuleModal.displayName = 'DuplicateRuleModal';

export default DuplicateRuleModal;
