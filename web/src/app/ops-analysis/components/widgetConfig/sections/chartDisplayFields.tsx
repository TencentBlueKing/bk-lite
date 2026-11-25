import React from 'react';
import { MinusCircleOutlined, PlusCircleOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { Button, ColorPicker, Form, Input, InputNumber, Switch, Tooltip } from 'antd';
import {
  CHART_DISPLAY_I18N,
  DEFAULT_SCROLL_SECONDS,
  referenceLineColor,
  chartDisplayControls,
} from '@/app/ops-analysis/utils/chartDisplay';
import type { OpsAnalysisWidgetSurface } from '@/app/ops-analysis/utils/chartTypeSurface';

interface ChartDisplayFieldsProps {
  t: (key: string) => string;
  chartType?: string;
  surface?: OpsAnalysisWidgetSurface;
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

const scrollSecondsText = (value: string | number | undefined | null): string => {
  if (value === undefined || value === null || value === '') return '';
  const numeric = Number(value);
  return Number.isFinite(numeric) ? String(numeric) : '';
};

const AutoScrollField = ({
  t,
  className,
}: {
  t: (key: string) => string;
  className: string;
}) => (
  <Form.Item
    className={className}
    label={(
      <CountLabel
        text={t(CHART_DISPLAY_I18N.autoScroll)}
        tip={t(CHART_DISPLAY_I18N.autoScrollTip)}
      />
    )}
    name="autoScroll"
    valuePropName="checked"
  >
    <Switch />
  </Form.Item>
);

const ScrollSecondsField = ({
  t,
  className,
}: {
  t: (key: string) => string;
  className: string;
}) => (
  <Form.Item
    className={className}
    label={t(CHART_DISPLAY_I18N.scrollSeconds)}
    name="scrollSeconds"
  >
    <InputNumber
      aria-label={t(CHART_DISPLAY_I18N.scrollSeconds)}
      min={0.5}
      max={30}
      step={0.5}
      className="w-full"
      formatter={scrollSecondsText}
      parser={(value) => {
        const numeric = Number(scrollSecondsText(value));
        return Number.isFinite(numeric) ? numeric : DEFAULT_SCROLL_SECONDS;
      }}
    />
  </Form.Item>
);

export const ChartDisplayFields: React.FC<ChartDisplayFieldsProps> = ({
  t,
  chartType,
  surface,
}) => {
  const controls = chartDisplayControls(chartType);
  const showAutoScroll = controls.autoScroll && surface === 'screen';
  const autoScrollOn = Form.useWatch('autoScroll') === true;
  const showScrollSeconds = showAutoScroll && autoScrollOn;
  const stackBesideSort = controls.sort && controls.stackBars;
  const rankingCount = Boolean(controls.limit && !controls.sort && !stackBesideSort);
  if (
    !controls.limit
    && !controls.sort
    && !controls.stackBars
    && !controls.referenceLines
    && !showAutoScroll
  ) {
    return null;
  }

  return (
    <div className="grid grid-cols-2 gap-x-4 [&_.ant-form-item]:!mb-0">
      {stackBesideSort ? (
        <div className="col-span-2 grid grid-cols-4 gap-x-4">
          {controls.limit ? (
            <Form.Item
              className="col-span-2 min-w-0"
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
          <Form.Item
            className="col-span-1 min-w-0"
            label={t(CHART_DISPLAY_I18N.sort)}
            name="sortByValue"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          <Form.Item
            className="col-span-1 min-w-0"
            label={t(CHART_DISPLAY_I18N.stackBars)}
            name="stackBars"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </div>
      ) : rankingCount ? (
        <div className="col-span-2 grid grid-cols-2 gap-x-4 gap-y-4">
          <Form.Item
            className="col-span-2 min-w-0"
            label={t(CHART_DISPLAY_I18N.count)}
            name="displayLimit"
          >
            <InputNumber
              min={1}
              precision={0}
              className="w-full"
              placeholder={t(CHART_DISPLAY_I18N.countPlaceholder)}
            />
          </Form.Item>
          {showAutoScroll ? <AutoScrollField t={t} className="min-w-0" /> : null}
          {showScrollSeconds ? <ScrollSecondsField t={t} className="min-w-0" /> : null}
        </div>
      ) : (
        <>
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
        </>
      )}
      {showAutoScroll && !rankingCount ? (
        <>
          <AutoScrollField t={t} className="min-w-0" />
          {showScrollSeconds ? <ScrollSecondsField t={t} className="min-w-0" /> : null}
        </>
      ) : null}
      {controls.referenceLines ? (
        <div className="col-span-2 mt-3">
          <Form.Item label={t(CHART_DISPLAY_I18N.referenceLines)} className="!mb-0">
            <Form.List name="referenceLines">
              {(fields, { add, remove }) => (
                <div className="rounded-xl bg-(--color-fill-2) p-3">
                    {fields.length === 0 ? (
                      <div className="py-1 text-xs text-(--color-text-3)">
                        {t(CHART_DISPLAY_I18N.referenceEmpty)}
                      </div>
                    ) : fields.map((field) => (
                      <div
                        key={field.key}
                        className="mb-1.5 flex items-center gap-1 rounded-lg bg-(--color-bg-1) px-2 py-0.5 last:mb-0"
                      >
                        <Form.Item
                          name={[field.name, 'color']}
                          className="!mb-0 shrink-0"
                          getValueFromEvent={(color: { toHexString?: () => string }, hex?: string) => {
                            const raw = typeof hex === 'string' && hex.startsWith('#')
                              ? hex
                              : color?.toHexString?.() ?? '';
                            const digits = raw.replace('#', '').slice(0, 6);
                            return digits.length === 6 ? `#${digits}` : referenceLineColor();
                          }}
                        >
                          <ColorPicker
                            size="small"
                            disabledAlpha
                            aria-label={t(CHART_DISPLAY_I18N.referenceColor)}
                            className="[&_.ant-color-picker-trigger]:!h-4 [&_.ant-color-picker-trigger]:!w-4 [&_.ant-color-picker-trigger]:!min-w-4 [&_.ant-color-picker-trigger]:!rounded-full [&_.ant-color-picker-trigger]:!border-0 [&_.ant-color-picker-trigger]:!p-0"
                          />
                        </Form.Item>
                        <Form.Item name={[field.name, 'name']} className="!mb-0 min-w-0 flex-1">
                          <Input
                            aria-label={t(CHART_DISPLAY_I18N.referenceName)}
                            placeholder={t(CHART_DISPLAY_I18N.referenceNamePlaceholder)}
                            variant="borderless"
                            size="small"
                          />
                        </Form.Item>
                        <span aria-hidden className="h-3.5 w-px shrink-0 bg-(--color-border-2)" />
                        <Form.Item name={[field.name, 'value']} className="!mb-0 w-24 shrink-0">
                          <InputNumber
                            aria-label={t(CHART_DISPLAY_I18N.referenceValue)}
                            placeholder={t(CHART_DISPLAY_I18N.referenceValuePlaceholder)}
                            variant="borderless"
                            size="small"
                            controls={false}
                            className="w-full"
                          />
                        </Form.Item>
                        <Button
                          type="text"
                          size="small"
                          className="shrink-0 text-(--color-text-3)"
                          aria-label={t('dashboard.referenceLineRemove')}
                          icon={<MinusCircleOutlined />}
                          onClick={() => remove(field.name)}
                        />
                      </div>
                    ))}
                    <Button
                      type="link"
                      size="small"
                      className="mt-1 px-0"
                      icon={<PlusCircleOutlined />}
                      onClick={() => add({ name: '', value: null, color: referenceLineColor() })}
                    >
                      {t(CHART_DISPLAY_I18N.referenceAdd)}
                    </Button>
                </div>
              )}
            </Form.List>
          </Form.Item>
        </div>
      ) : null}
    </div>
  );
};
