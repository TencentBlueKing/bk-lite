import React from 'react';
import { Form, Input } from 'antd';
import type { CSSProperties } from 'react';
import GroupTreeSelector from '@/components/group-tree-select';

interface EventStrategyIdentityFieldsProps {
  strategyNameLabel: React.ReactNode;
  strategyNamePlaceholder: string;
  organizationLabel: React.ReactNode;
  organizationPlaceholder: string;
  requiredMessage: string;
  strategyDescription?: React.ReactNode;
  organizationDescription?: React.ReactNode;
  strategyInputClassName?: string;
  strategyInputStyle?: CSSProperties;
  organizationSelectorStyle?: CSSProperties;
}

const EventStrategyIdentityFields: React.FC<
  EventStrategyIdentityFieldsProps
> = ({
  strategyNameLabel,
  strategyNamePlaceholder,
  organizationLabel,
  organizationPlaceholder,
  requiredMessage,
  strategyDescription,
  organizationDescription,
  strategyInputClassName,
  strategyInputStyle,
  organizationSelectorStyle,
}) => {
  return (
    <>
      <Form.Item
        label={strategyNameLabel}
        name="name"
        rules={[{ required: true, message: requiredMessage }]}
      >
        <Input
          placeholder={strategyNamePlaceholder}
          className={strategyInputClassName}
          style={strategyInputStyle}
        />
      </Form.Item>

      {strategyDescription ? (
        <div className="mt-[-10px] mb-[24px] text-[var(--color-text-3)]">
          {strategyDescription}
        </div>
      ) : null}

      <Form.Item required label={organizationLabel}>
        <Form.Item
          name="organizations"
          noStyle
          rules={[{ required: true, message: requiredMessage }]}
        >
          <GroupTreeSelector
            style={organizationSelectorStyle}
            placeholder={organizationPlaceholder}
          />
        </Form.Item>
        {organizationDescription ? (
          <div className="text-[var(--color-text-3)] mt-[10px]">
            {organizationDescription}
          </div>
        ) : null}
      </Form.Item>
    </>
  );
};

export default EventStrategyIdentityFields;
