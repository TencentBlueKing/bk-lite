import React from 'react';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Form, Input, Select } from 'antd';
import { ChartRoleLabel } from './chartRoleLabel';

interface PieScalarFieldsSectionProps {
  t: (key: string) => string;
  options: Array<{ label: React.ReactNode; value: string }>;
  disabled?: boolean;
}

export const PieScalarFieldsSection: React.FC<PieScalarFieldsSectionProps> = ({
  t,
  options,
  disabled = false,
}) => (
  <div className="mb-4">
    <Form.Item
      className="!mb-2"
      label={(
        <ChartRoleLabel
          text={t('dashboard.pieScalarFields')}
          tip={t('dashboard.pieScalarFieldsTip')}
        />
      )}
    >
      <Form.List name="pieScalarFields">
        {(fields, { add, remove }) => (
          <div className="space-y-2">
            {fields.map((field) => (
              <div
                key={field.key}
                className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-start gap-2"
              >
                <Form.Item
                  name={[field.name, 'field']}
                  className="!mb-0"
                >
                  <Select
                    allowClear
                    disabled={disabled}
                    showSearch
                    optionFilterProp="value"
                    options={options}
                    placeholder={t('dashboard.pieScalarField')}
                  />
                </Form.Item>
                <Form.Item name={[field.name, 'label']} className="!mb-0">
                  <Input
                    disabled={disabled}
                    placeholder={t('dashboard.pieScalarLabel')}
                  />
                </Form.Item>
                <Button
                  type="text"
                  aria-label={t('dashboard.pieScalarRemove')}
                  icon={<MinusCircleOutlined />}
                  onClick={() => remove(field.name)}
                />
              </div>
            ))}
            <Button
              type="dashed"
              block
              icon={<PlusOutlined />}
              disabled={disabled}
              onClick={() => add({})}
            >
              {t('dashboard.pieScalarFields')}
            </Button>
          </div>
        )}
      </Form.List>
    </Form.Item>
  </div>
);
