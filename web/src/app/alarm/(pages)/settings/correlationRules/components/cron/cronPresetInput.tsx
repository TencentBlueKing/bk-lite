import React, { useEffect, useMemo, useState } from 'react';
import { Form, Input, Select, Typography } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  CronPresetKey,
  CUSTOM_PRESET,
  PRESET_CRONS,
  getCronDescription,
} from './cronPresetUtils';

interface CronPresetInputProps {
  value?: string;
  onChange?: (value: string) => void;
}

const CronPresetInput: React.FC<CronPresetInputProps> = ({ value, onChange }) => {
  const { t } = useTranslation();
  const [preset, setPreset] = useState<CronPresetKey>(CUSTOM_PRESET);
  const { status, errors } = Form.Item.useStatus();

  const labelClassName = 'w-[100px] shrink-0 pr-2 pt-[5px] text-right text-sm text-gray-600';
  const controlClassName = 'w-[420px]';
  const getEveryNMinutesLabel = (minutes: number) => t('settings.correlation.cronPreset.everyNMinutes').replace('{n}', `${minutes}`);

  const presetOptions = useMemo(
    () => [
      { value: CUSTOM_PRESET, label: t('settings.correlation.cronPreset.custom') },
      {
        value: 'every3Minutes' as const,
        label: getEveryNMinutesLabel(3),
      },
      {
        value: 'every5Minutes' as const,
        label: getEveryNMinutesLabel(5),
      },
      {
        value: 'every10Minutes' as const,
        label: getEveryNMinutesLabel(10),
      },
      {
        value: 'every15Minutes' as const,
        label: getEveryNMinutesLabel(15),
      },
      {
        value: 'every30Minutes' as const,
        label: getEveryNMinutesLabel(30),
      },
      { value: 'hourly' as const, label: t('settings.correlation.cronPreset.hourly') },
      { value: 'daily9am' as const, label: t('settings.correlation.cronPreset.daily9am') },
      {
        value: 'daily12pm' as const,
        label: t('settings.correlation.cronPreset.daily12pm'),
      },
      { value: 'daily6pm' as const, label: t('settings.correlation.cronPreset.daily6pm') },
      {
        value: 'weekdays9am' as const,
        label: t('settings.correlation.cronPreset.weekdays9am'),
      },
      {
        value: 'weekdays6pm' as const,
        label: t('settings.correlation.cronPreset.weekdays6pm'),
      },
      {
        value: 'monday9am' as const,
        label: t('settings.correlation.cronPreset.monday9am'),
      },
      {
        value: 'friday6pm' as const,
        label: t('settings.correlation.cronPreset.friday6pm'),
      },
      {
        value: 'firstDay9am' as const,
        label: t('settings.correlation.cronPreset.firstDay9am'),
      },
    ],
    [t]
  );

  useEffect(() => {
    const foundPreset = Object.entries(PRESET_CRONS).find(([, cron]) => cron === value);
    if (foundPreset) {
      setPreset(foundPreset[0] as CronPresetKey);
    } else {
      setPreset(CUSTOM_PRESET);
    }
  }, [value]);

  const handlePresetChange = (newPreset: CronPresetKey) => {
    setPreset(newPreset);
    if (newPreset !== CUSTOM_PRESET) {
      onChange?.(PRESET_CRONS[newPreset]);
    }
  };

  const description = useMemo(() => getCronDescription(value || '', t), [t, value]);
  const errorMessage = status === 'error' ? errors[0] : null;

  return (
    <div className="space-y-3">
      <div className="flex items-start">
        <div className={labelClassName}>
          {t('settings.correlation.quickSelect')}
        </div>
        <div className={controlClassName}>
          <Select
            value={preset}
            options={presetOptions}
            onChange={handlePresetChange}
            className="w-full"
            popupMatchSelectWidth={false}
          />
        </div>
      </div>

      <div className="flex items-start">
        <div className={labelClassName}>
          <span className="break-all">{t('settings.correlation.cronExpression')}</span>
        </div>
        <div className={controlClassName}>
          <Input
            value={value}
            status={status === 'error' ? 'error' : undefined}
            onChange={(e) => onChange?.(e.target.value)}
            placeholder="e.g. */5 * * * *"
          />
          {errorMessage ? (
            <div className="mt-1 text-xs leading-5 text-[#ff4d4f]">{errorMessage}</div>
          ) : (
            description && (
              <Typography.Text type="secondary" className="mt-1 block text-sm leading-5">
                {description}
              </Typography.Text>
            )
          )}
        </div>
      </div>
    </div>
  );
};

export default CronPresetInput;
