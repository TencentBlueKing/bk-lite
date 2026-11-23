import React from 'react';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { Form, InputNumber, Switch, Tooltip } from 'antd';
import {
  CHART_DISPLAY_I18N,
  chartDisplayControls,
} from '@/app/ops-analysis/utils/chartDisplay';

interface ChartDisplayFieldsProps {
  t: (key: string) => string;
  chartType?: string;
}

const CountLabel = ({
  text,
  tip,
}: {
  text: string;
  tip?: string;
}) => (
  <span>
    {text}
    {tip ? (
      <Tooltip title={tip} styles={{ body: { maxWidth: 360 } }}>
        <QuestionCircleOutlined
          aria-label={tip}
          className="ml-1 cursor-help text-(--color-text-3)"
        />
      </Tooltip>
    ) : null}
  </span>
);

export const ChartDisplayFields: React.FC<ChartDisplayFieldsProps> = ({
  t,
  chartType,
}) => {
  const controls = chartDisplayControls(chartType);
  if (!controls.limit && !controls.sort) return null;

  return (
    <div className="grid grid-cols-2 gap-x-4 [&_.ant-form-item]:!mb-0">
      {controls.limit ? (
        <Form.Item
          className="min-w-0"
          label={(
            <CountLabel
              text={t(CHART_DISPLAY_I18N.count)}
              tip={chartType === 'bar' ? t(CHART_DISPLAY_I18N.timeIgnored) : undefined}
            />
          )}
          name="displayLimit"
        >
          <InputNumber
            min={1}
            precision={0}
            className="w-full"
            placeholder={t(CHART_DISPLAY_I18N.countPlaceholder)}
          />
        </Form.Item>
      ) : null}
      {controls.sort ? (
        <Form.Item
          className="min-w-0"
          label={t(CHART_DISPLAY_I18N.sort)}
          name="sortByValue"
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      ) : null}
    </div>
  );
};
