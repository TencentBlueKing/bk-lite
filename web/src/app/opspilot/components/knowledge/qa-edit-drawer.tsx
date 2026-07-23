'use client';

import React, { useEffect, useState } from 'react';
import { Button, Drawer, Form, Input, Space } from 'antd';

export interface KnowledgeQAEditValues {
  question: string;
  answer: string;
}

export interface KnowledgeQAEditDrawerProps {
  visible: boolean;
  onClose: () => void;
  onSubmit: (values: KnowledgeQAEditValues) => Promise<void> | void;
  onSubmitAndContinue?: (values: KnowledgeQAEditValues) => Promise<void> | void;
  showContinueButton?: boolean;
  title?: string;
  initialData?: Partial<KnowledgeQAEditValues>;
}

const KnowledgeQAEditDrawer: React.FC<KnowledgeQAEditDrawerProps> = ({
  visible,
  onClose,
  onSubmit,
  onSubmitAndContinue,
  showContinueButton = false,
  title = 'Create QA pair',
  initialData,
}) => {
  const [form] = Form.useForm<KnowledgeQAEditValues>();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (visible) {
      form.setFieldsValue({
        question: initialData?.question ?? '',
        answer: initialData?.answer ?? '',
      });
    }
  }, [visible, initialData, form]);

  const handleSubmit = async (continueEdit: boolean) => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      if (continueEdit && onSubmitAndContinue) {
        await onSubmitAndContinue(values);
        form.resetFields();
      } else {
        await onSubmit(values);
        onClose();
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      open={visible}
      onClose={onClose}
      title={title}
      width={520}
      destroyOnClose
      extra={
        <Space>
          <Button onClick={onClose}>Cancel</Button>
          {showContinueButton && onSubmitAndContinue ? (
            <Button loading={submitting} onClick={() => handleSubmit(true)}>
              Save and continue
            </Button>
          ) : null}
          <Button type="primary" loading={submitting} onClick={() => handleSubmit(false)}>
            Save
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="question"
          label="Question"
          rules={[{ required: true, message: 'Question is required' }]}
        >
          <Input.TextArea autoSize={{ minRows: 2, maxRows: 6 }} />
        </Form.Item>
        <Form.Item
          name="answer"
          label="Answer"
          rules={[{ required: true, message: 'Answer is required' }]}
        >
          <Input.TextArea autoSize={{ minRows: 4, maxRows: 12 }} />
        </Form.Item>
      </Form>
    </Drawer>
  );
};

export default KnowledgeQAEditDrawer;
