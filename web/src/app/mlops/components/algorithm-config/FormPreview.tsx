'use client';
import React from 'react';
import {
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  Divider,
  Empty,
} from 'antd';
import type { FormConfig, GroupConfig, FieldConfig } from '@/app/mlops/types/algorithmConfig';

interface FormPreviewProps {
  formConfig: FormConfig;
}

/**
 * 表单预览组件
 * 根据 formConfig 渲染表单预览，风格与训练任务表单保持一致
 */
const FormPreview = ({ formConfig }: FormPreviewProps) => {
  /**
   * 渲染单个字段
   */
  const renderField = (field: FieldConfig, index: number) => {
    const nameStr = Array.isArray(field.name) ? field.name.join('.') : field.name;
    const key = `${nameStr}-${index}`;

    const commonProps = {
      name: field.name,
      label: field.label,
      rules: field.required ? [{ required: true, message: `请输入${field.label}` }] : undefined,
      tooltip: field.tooltip,
      initialValue: field.defaultValue,
    };

    let fieldElement: React.ReactNode;

    switch (field.type) {
      case 'input':
        fieldElement = <Input placeholder={field.placeholder} />;
        break;

      case 'inputNumber':
        fieldElement = (
          <InputNumber
            style={{ width: '100%' }}
            min={field.min}
            max={field.max}
            step={field.step}
            placeholder={field.placeholder}
          />
        );
        break;

      case 'select':
        fieldElement = (
          <Select
            placeholder={field.placeholder}
            options={field.options}
          />
        );
        break;

      case 'multiSelect':
        fieldElement = (
          <Select
            mode="multiple"
            placeholder={field.placeholder}
            maxTagCount={3}
            options={field.options}
          />
        );
        break;

      case 'switch':
        return (
          <Form.Item
            key={key}
            {...commonProps}
            valuePropName="checked"
          >
            <Switch size="small" />
          </Form.Item>
        );

      case 'stringArray':
        fieldElement = <Input placeholder={field.placeholder} />;
        break;

      default:
        fieldElement = <Input placeholder={field.placeholder} />;
    }

    return (
      <Form.Item key={key} {...commonProps}>
        {fieldElement}
      </Form.Item>
    );
  };

  /**
   * 渲染一个字段组
   */
  const renderGroup = (group: GroupConfig, groupIndex: number) => {
    if (!group.fields || group.fields.length === 0) return null;

    return (
      <React.Fragment key={`${group.title || 'group'}-${groupIndex}`}>
        {/* 组标题 - 使用 Divider 与训练表单一致 */}
        {group.title && (
          <Divider orientation="left" orientationMargin="0" plain style={{ borderColor: '#d1d5db' }}>
            {group.title}
          </Divider>
        )}

        {/* 子标题 */}
        {group.subtitle && (
          <div style={{ marginTop: group.title ? 0 : 20, marginBottom: 12, color: '#666', fontSize: 13, fontWeight: 500 }}>
            {group.subtitle}
          </div>
        )}

        {/* 字段渲染 */}
        {group.fields.map((field, fieldIndex) => renderField(field, fieldIndex))}
      </React.Fragment>
    );
  };

  // 检查是否有配置内容
  const hasHyperparams = formConfig.groups.hyperparams?.length > 0;
  const hasPreprocessing = formConfig.groups.preprocessing?.length > 0;
  const hasFeatureEngineering = formConfig.groups.feature_engineering?.length > 0;
  const hasContent = hasHyperparams || hasPreprocessing || hasFeatureEngineering;

  if (!hasContent) {
    return (
      <Empty
        description="请在表单配置标签页中编辑 JSON 配置"
        className="py-12"
      />
    );
  }

  return (
    <div>
      <Form layout="vertical">
        {/* Hyperparams 组 */}
        {formConfig.groups.hyperparams?.map((group, index) => renderGroup(group, index))}

        {/* Preprocessing 组 */}
        {formConfig.groups.preprocessing?.map((group, index) => renderGroup(group, index))}

        {/* Feature Engineering 组 */}
        {formConfig.groups.feature_engineering?.map((group, index) => renderGroup(group, index))}
      </Form>
    </div>
  );
};

export default FormPreview;
