import React from 'react';
import { Form, Input, Select, InputNumber, Switch, FormInstance } from 'antd';
import EditablePasswordField from './editPasswordField'; // Import EditablePasswordField

interface Field {
  name: string;
  type: string;
  label: string;
  placeholder?: string;
  rules?: any[];
  options?: { value: string | number; label: string }[];
  component?: React.ReactNode;
  [key: string]: any;
}

interface DynamicFormProps {
  form: FormInstance;
  fields: Field[];
  initialValues?: { [key: string]: any };
}

const componentMap: { [key: string]: React.FC<any> } = {
  input: (props) => <Input {...props} />,
  inputPwd: (props) => <Input.Password {...props} />,
  editablePwd: (props) => <EditablePasswordField {...props} />,
  textarea: (props) => <Input.TextArea {...props} />,
  switch: (props) => <Switch {...props} />,
  select: ({ options, ...props }) => (
    <Select {...props}>
      {options?.map((option: any) => (
        <Select.Option key={option.value} value={option.value}>
          {option.label}
        </Select.Option>
      ))}
    </Select>
  ),
  inputNumber: (props) => <InputNumber {...props} />,
};

const DynamicForm: React.FC<DynamicFormProps> = ({ form, fields, initialValues }) => {
  return (
    <Form form={form} layout="vertical" initialValues={initialValues}>
      {fields.map((field) => {
        const Component = componentMap[field.type];
        const { name, label, rules, initialValue, ...rest } = field;

        return (
          <Form.Item
            key={name}
            name={name}
            label={label}
            rules={rules}
            initialValue={initialValue}
          >
            {/* 显式传递 value 和 onChange */}
            {Component ? (
              <Component {...rest} />
            ) : (
              field.component || null
            )}
          </Form.Item>
        );
      })}
    </Form>
  );
};

export default DynamicForm;
