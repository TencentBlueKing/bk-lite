import React from 'react';
import { Button, ColorPicker, Form, InputNumber } from 'antd';
import { MinusCircleOutlined, PlusCircleOutlined } from '@ant-design/icons';
import type { ThresholdColorConfig } from '@/components/ops-analysis-config-sections/types';

interface ThresholdColorConfigSectionProps {
  t: (key: string, defaultMessage?: string) => string;
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
}

export const ThresholdColorConfigSection: React.FC<
  ThresholdColorConfigSectionProps
> = ({
  t,
  thresholdColors,
  onThresholdChange,
  onThresholdBlur,
  onAddThreshold,
  onRemoveThreshold,
  readonly = false,
}) => {
  return (
    <Form.Item label={t('topology.nodeConfig.thresholdColors')}>
      <div className="rounded-md border border-(--color-border-1) bg-(--color-fill-1) px-3 py-2">
        {thresholdColors.map((threshold, index) => {
          const isBaseThreshold = index === thresholdColors.length - 1;
          return (
            <div key={index} className="flex items-center gap-2 py-1.5">
              <div className="flex items-center gap-3">
                <span className="text-sm text-gray-600 whitespace-nowrap">
                  {t('topology.nodeConfig.thresholdWhenValueGte')}
                </span>
                <InputNumber
                  value={parseFloat(threshold.value)}
                  onChange={(value) =>
                    onThresholdChange(index, 'value', value || 0)
                  }
                  onBlur={(e) => {
                    if (!isBaseThreshold && !readonly) {
                      const value = parseFloat(e.target.value);
                      onThresholdBlur(index, isNaN(value) ? 0 : value);
                    }
                  }}
                  placeholder={t('common.inputMsg')}
                  disabled={isBaseThreshold || readonly}
                  style={{ width: '100px' }}
                  size="small"
                  min={0}
                />
                <span className="text-sm text-gray-600">
                  {t('topology.nodeConfig.thresholdShow')}
                </span>
              </div>
              <ColorPicker
                value={threshold.color}
                onChange={(color) =>
                  onThresholdChange(index, 'color', color.toHexString())
                }
                disabled={readonly}
                size="small"
                showText
              />
              {!readonly ? (
                <div className="flex items-center gap-1 pl-2">
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
                      isBaseThreshold
                        ? t('topology.nodeConfig.baseThresholdNotRemovable')
                        : t('topology.nodeConfig.removeThreshold')
                    }
                    disabled={isBaseThreshold}
                    onClick={() => onRemoveThreshold(index)}
                  />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </Form.Item>
  );
};
