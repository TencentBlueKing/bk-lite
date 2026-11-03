import React, { forwardRef, useEffect, useImperativeHandle, useState } from 'react';
import { Alert, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ToolVariable } from '@/app/opspilot/types/tool';
import { useSkillApi } from '@/app/opspilot/api/skill';

export interface MlopsToolEditorHandle {
  save: () => boolean;
}

interface MlopsToolEditorProps {
  initialKwargs: ToolVariable[];
  onSave: (kwargs: ToolVariable[]) => void;
}

export const parseMlopsServingId = (kwargs: ToolVariable[] = []): number | null => {
  const raw = kwargs.find((item) => item.key === 'serving_ids')?.value;
  if (raw == null || raw === '') return null;
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    const first = Array.isArray(parsed) ? parsed[0] : parsed;
    const id = Number(first);
    return Number.isInteger(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
};

const MlopsToolEditor = forwardRef<MlopsToolEditorHandle, MlopsToolEditorProps>(({ initialKwargs, onSave }, ref) => {
  const { t } = useTranslation();
  const { fetchTimeseriesPredictServings } = useSkillApi();
  const [servingId, setServingId] = useState<number | null>(parseMlopsServingId(initialKwargs));
  const [options, setOptions] = useState<{ value: number; label: string }[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    fetchTimeseriesPredictServings()
      .then((items) => {
        if (cancelled) return;
        setOptions(items.map((item) => ({ value: item.id, label: `${item.name} (${item.id})` })));
      })
      .catch(() => {
        if (!cancelled) setError(t('tool.mlops.loadFailed', '加载预测服务失败'));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useImperativeHandle(ref, () => ({
    save: () => {
      if (!servingId) {
        setError(t('tool.mlops.servingRequired', '请选择一个时序预测服务'));
        return false;
      }
      onSave([
        {
          key: 'serving_ids',
          value: JSON.stringify([servingId]),
          type: 'string',
          isRequired: true,
        },
      ]);
      return true;
    },
  }));

  return (
    <div className="flex flex-col gap-3">
      <Select
        className="w-full"
        value={servingId ?? undefined}
        options={options}
        placeholder={t('tool.mlops.servingPlaceholder', '选择一个时序预测服务')}
        onChange={(value) => {
          setServingId(value);
          setError('');
        }}
      />
      {error ? <Alert type="error" showIcon message={error} /> : null}
    </div>
  );
});

MlopsToolEditor.displayName = 'MlopsToolEditor';
export default MlopsToolEditor;
