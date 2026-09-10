import React from 'react';
import { Button, ColorPicker, Form, InputNumber } from 'antd';
import { MinusCircleOutlined, PlusCircleOutlined } from '@ant-design/icons';
import type { ThresholdColorConfig } from '@/app/ops-analysis/components/ops-analysis-config-sections/types';

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
      <div className="rounded-lg border border-(--color-border-1) bg-(--color-fill-1)/40 p-2.5 space-y-1.5">
        {thresholdColors.map((threshold, index) => {
          const isBaseThreshold = index === thresholdColors.length - 1;
          return (
            <div
              key={index}
              className="flex items-center justify-between gap-2 rounded-md bg-(--color-bg) px-3 py-1.5 border border-(--color-border-1)/60 shadow-xs"
            >
              <div className="flex items-center gap-2 text-xs text-(--color-text-2)">
                <span className="whitespace-nowrap">
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
                  className="!w-24"
                  size="small"
                  min={0}
                />
                <span className="whitespace-nowrap text-(--color-text-3)">
                  {t('topology.nodeConfig.thresholdShow')}
                </span>
              </div>
              <div className="flex items-center gap-2">
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
                  <div className="flex items-center gap-0.5">
                    <Button
                      type="text"
                      size="small"
                      icon={<PlusCircleOutlined className="text-(--color-text-3) hover:text-(--color-primary)" />}
                      title={t('topology.nodeConfig.addThresholdBelow')}
                      onClick={() => onAddThreshold(index)}
                    />
                    <Button
                      type="text"
                      size="small"
                      icon={<MinusCircleOutlined className={isBaseThreshold ? 'text-(--color-text-4)' : 'text-(--color-text-3) hover:text-(--color-fail)'} />}
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
            </div>
          );
        })}
      </div>
    </Form.Item>
  );
};
