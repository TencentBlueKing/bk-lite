import React from 'react';
import { Form, Input, InputNumber, Select, Switch, Divider } from 'antd';
import type { AlgorithmConfig, FieldConfig, GroupConfig } from '@/app/mlops/types/task';
import { get } from 'lodash';

interface AlgorithmFieldRendererProps {
  config: AlgorithmConfig;
  // 用于判断依赖字段的值（用于控制显示/隐藏）
  formValues: any;
}

export const AlgorithmFieldRenderer: React.FC<AlgorithmFieldRendererProps> = ({
  config,
  formValues,
}) => {
  /**
   * 检查字段是否应该显示（基于 dependencies）
   * dependencies 格式：[['path', 'to', 'field1'], ['path', 'to', 'field2']]
   * 所有依赖条件必须同时满足（AND 逻辑）
   */
  const shouldShowField = (field: FieldConfig): boolean => {
    if (!field.dependencies || field.dependencies.length === 0) {
      return true;
    }

    // 检查所有依赖条件，必须全部为 true
    return field.dependencies.every(dep => !!get(formValues, dep));
  };

  /**
   * 渲染单个字段
   */
  const renderField = (field: FieldConfig) => {
    if (!shouldShowField(field)) {
      return null;
    }

    const commonProps = {
      name: field.name,
      label: field.label,
      rules: field.required ? [{ required: true, message: `请输入${field.label}` }] : undefined,
      tooltip: field.tooltip,
      layout: (field.layout === 'horizontal' ? 'horizontal' : undefined) as any,
    };

    let fieldElement;

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
            key={JSON.stringify(field.name)}
            {...commonProps}
            valuePropName="checked"
          >
            <Switch defaultChecked={field.defaultValue} size="small" />
          </Form.Item>
        );

      case 'stringArray':
        fieldElement = <Input placeholder={field.placeholder} />;
        break;

      default:
        fieldElement = <Input placeholder={field.placeholder} />;
    }

    return (
      <Form.Item key={JSON.stringify(field.name)} {...commonProps}>
        {fieldElement}
      </Form.Item>
    );
  };

  /**
   * 渲染一个字段组
   */
  const renderGroup = (group: GroupConfig, groupIndex: number) => {
    const visibleFields = group.fields.filter(shouldShowField);
    if (visibleFields.length === 0) return null;

    return (
      <React.Fragment key={`${group.title || 'group'}-${groupIndex}`}>
        {/* 组标题 */}
        {group.title && (
          <Divider orientation="start" orientationMargin="0" plain style={{ borderColor: '#d1d5db' }}>
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
        {group.fields.map((field) => renderField(field))}
      </React.Fragment>
    );
  };

  return (
    <>
      {/* Hyperparams 组 */}
      {config.groups.hyperparams?.map((group, index) => renderGroup(group, index))}

      {/* Preprocessing 组 */}
      {config.groups.preprocessing?.map((group, index) => renderGroup(group, index))}

      {/* Feature Engineering 组 */}
      {config.groups.feature_engineering?.map((group, index) => renderGroup(group, index))}
    </>
  );
};
