import React from 'react';
import { Button, ColorPicker, Form, InputNumber } from 'antd';
import { MinusCircleOutlined, PlusCircleOutlined } from '@ant-design/icons';
import type { ThresholdColorConfig } from '@/app/ops-analysis/utils/thresholdUtils';

interface ThresholdColorConfigSectionProps {
  t: (key: string, defaultMessage?: string) => string;
  label?: React.ReactNode;
  extra?: React.ReactNode;
  thresholdColors: ThresholdColorConfig[];
  onThresholdChange: (
    index: number,
    field: 'value' | 'color',
    value: string | number,
  ) => void;
  onThresholdBlur: (index: number, value: number | null) => void;
  onAddThreshold: (afterIndex?: number) => void;
  onRemoveThreshold: (index: number) => void;
  readonly?: boolean;
  /** 允许空列表（指标列表等：未配置时不上色，并可删光） */
  allowEmpty?: boolean;
}

export const ThresholdColorConfigSection: React.FC<
  ThresholdColorConfigSectionProps
> = ({
  t,
  label,
  extra,
  thresholdColors,
  onThresholdChange,
  onThresholdBlur,
  onAddThreshold,
  onRemoveThreshold,
  readonly = false,
  allowEmpty = false,
}) => {
  return (
    <Form.Item
      label={label ?? t('topology.nodeConfig.thresholdColors')}
      extra={extra}
    >
      <div className="rounded-xl bg-(--color-fill-2) p-3">
        {thresholdColors.map((threshold, index) => {
          const isBaseThreshold = index === thresholdColors.length - 1;
          return (
            <div key={index} className="flex items-center gap-2 py-1.5">
              <div className="flex min-w-0 items-center gap-3">
                <span className="shrink-0 whitespace-nowrap text-xs text-(--color-text-2)">
                  {t('topology.nodeConfig.thresholdWhenValueGte')}
                </span>
                <InputNumber
                  value={parseFloat(threshold.value)}
                  onChange={(value) =>
                    onThresholdChange(index, 'value', value || 0)
                  }
                  onBlur={(e) => {
                    if (!readonly && (!isBaseThreshold || allowEmpty)) {
                      const value = parseFloat(e.target.value);
                      onThresholdBlur(index, isNaN(value) ? 0 : value);
                    }
                  }}
                  placeholder={t('common.inputMsg')}
                  disabled={(isBaseThreshold && !allowEmpty) || readonly}
                  className="min-w-0 shrink"
                  style={{ width: '100px' }}
                  size="small"
                  min={0}
                />
                <span className="shrink-0 whitespace-nowrap text-xs text-(--color-text-2)">
                  {t('topology.nodeConfig.thresholdShow')}
                </span>
              </div>
              <ColorPicker
                className="shrink-0 !items-center [&_.ant-color-picker-trigger-text]:whitespace-nowrap"
                value={threshold.color}
                onChange={(color) =>
                  onThresholdChange(index, 'color', color.toHexString())
                }
                disabled={readonly}
                size="small"
                showText
              />
              {!readonly ? (
                <div className="flex shrink-0 items-center gap-1 pl-2">
                  <Button
                    type="text"
                    size="small"
                    icon={<PlusCircleOutlined />}
                    title={t('topology.nodeConfig.addThresholdBelow')}
                    onClick={() => onAddThreshold(index)}
                  />
                  <Button
                    type="text"
                    size="small"
                    icon={<MinusCircleOutlined />}
                    title={
                      isBaseThreshold && !allowEmpty
                        ? t('topology.nodeConfig.baseThresholdNotRemovable')
                        : t('topology.nodeConfig.removeThreshold')
                    }
                    disabled={!allowEmpty && isBaseThreshold}
                    onClick={() => onRemoveThreshold(index)}
                  />
                </div>
              ) : null}
            </div>
          );
        })}
        {allowEmpty && thresholdColors.length === 0 && !readonly ? (
          <Button
            type="dashed"
            size="small"
            icon={<PlusCircleOutlined />}
            onClick={() => onAddThreshold()}
          >
            {t('topology.nodeConfig.addThresholdBelow')}
          </Button>
        ) : null}
      </div>
    </Form.Item>
  );
};
