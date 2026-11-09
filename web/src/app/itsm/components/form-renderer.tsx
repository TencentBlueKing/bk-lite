'use client';

import { Form, Input, InputNumber, Select } from 'antd';
import type { FormSchema } from '../types';

interface FormRendererProps {
  schema: FormSchema;
  onSubmit: (values: Record<string, unknown>) => void;
}

export function FormRenderer({ schema, onSubmit }: FormRendererProps) {
  return (
    <Form layout="vertical" onFinish={(values) => onSubmit(values as Record<string, unknown>)}>
      {schema.fields.map((field) => (
        <Form.Item key={field.key} name={field.key} label={field.label} rules={field.required ? [{ required: true }] : []}>
          {field.type === 'number' ? <InputNumber className="w-full" /> : field.type === 'select' ? <Select options={field.source?.options || []} /> : <Input />}
        </Form.Item>
      ))}
    </Form>
  );
}
