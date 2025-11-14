import React from 'react';
import { Button, Input, Select, Checkbox, Row, Col } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { PlusOutlined, MinusOutlined } from '@ant-design/icons';

interface VariableListProps {
  value?: { key: string; type: string; isRequired: boolean }[];
  onChange?: (value: { key: string; type: string; isRequired: boolean }[]) => void;
  disabled?: boolean;
}

const VariableList: React.FC<VariableListProps> = ({ value = [], onChange, disabled = false }) => {
  const { t } = useTranslation();
  const variables = value.length > 0 ? value : [{ key: '', type: 'text', isRequired: false }];

  const handleAdd = () => {
    const updatedVariables = [...variables, { key: '', type: 'text', isRequired: false }];
    onChange?.(updatedVariables);
  };

  const handleDelete = (index: number) => {
    const updatedVariables = variables.filter((_, i) => i !== index);
    onChange?.(updatedVariables);
  };

  const handleChange = (key: string, value: any, index: number) => {
    if (!variables) return;
    const updatedVariables = [...variables];
    updatedVariables[index] = { ...updatedVariables[index], [key]: value };
    onChange?.(updatedVariables);
  };

  return (
    <div className="space-y-2">
      {variables.map((variable, index) => (
        <Row key={index} gutter={8} align="middle" className="mb-2">
          <Col span={6}>
            <Select
              value={variable.type}
              onChange={(value) => handleChange('type', value, index)}
              style={{ width: '100%' }}
              disabled={disabled}
              options={[
                { value: 'text', label: t('tool.text') },
                { value: 'password', label: t('tool.password') },
              ]}
            />
          </Col>
          <Col span={10}>
            <Input
              value={variable.key}
              onChange={(e) => handleChange('key', e.target.value, index)}
              placeholder={t('tool.variables')}
              style={{ width: '100%' }}
              disabled={disabled}
            />
          </Col>
          <Col span={5}>
            <Checkbox
              checked={variable.isRequired}
              onChange={(e) => handleChange('isRequired', e.target.checked, index)}
              disabled={disabled}
            >
              {t('common.required')}
            </Checkbox>
          </Col>
          <Col span={3}>
            <Button
              size="small"
              type="text"
              shape="circle"
              icon={<PlusOutlined />}
              onClick={handleAdd}
              disabled={disabled}
            />
            <Button
              size="small"
              type="text"
              shape="circle"
              icon={<MinusOutlined />}
              onClick={() => handleDelete(index)}
              disabled={disabled || index === 0}
              className="ml-1"
            />
          </Col>
        </Row>
      ))}
    </div>
  );
};

export default VariableList;