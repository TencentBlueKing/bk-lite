'use client';

import { Form, Input } from 'antd';
import { forwardRef, useEffect, useImperativeHandle, useState } from 'react';

import { useTranslation } from '@/utils/i18n';

export interface JsonValueInputHandle {
  validate: () => { valid: true; value: unknown } | { valid: false };
}

interface JsonValueInputProps {
  value: unknown;
  onChange: (value: unknown) => void;
  rows?: number;
  disabled?: boolean;
  required?: boolean;
  expectedType?: 'object' | 'array' | 'any';
  ariaLabel?: string;
}

function serialize(value: unknown) {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export const JsonValueInput = forwardRef<JsonValueInputHandle, JsonValueInputProps>(function JsonValueInput({
  value,
  onChange,
  rows = 12,
  disabled = false,
  required = false,
  expectedType = 'any',
  ariaLabel,
}, ref) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(() => serialize(value));
  const [error, setError] = useState('');

  useEffect(() => {
    setDraft(serialize(value));
    setError('');
  }, [value]);

  const validate = (): { valid: true; value: unknown } | { valid: false } => {
    const raw = draft.trim();
    if (!raw) {
      if (required) {
        setError(t('workflowOrchestration.form.jsonRequired', '请填写 JSON 数据'));
        return { valid: false };
      }
      setError('');
      onChange(undefined);
      return { valid: true, value: undefined };
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      setError(t('workflowOrchestration.form.invalidJson', '请输入有效的 JSON'));
      return { valid: false };
    }
    if (expectedType === 'object' && (!parsed || typeof parsed !== 'object' || Array.isArray(parsed))) {
      setError(t('workflowOrchestration.form.jsonObjectRequired', '请输入 JSON 对象'));
      return { valid: false };
    }
    if (expectedType === 'array' && !Array.isArray(parsed)) {
      setError(t('workflowOrchestration.form.jsonArrayRequired', '请输入 JSON 数组'));
      return { valid: false };
    }
    setError('');
    onChange(parsed);
    return { valid: true, value: parsed };
  };

  useImperativeHandle(ref, () => ({ validate }), [draft, expectedType, onChange, required, t]);

  return <div>
    <Input.TextArea
      aria-label={ariaLabel}
      className="font-mono text-xs"
      disabled={disabled}
      rows={rows}
      status={error ? 'error' : undefined}
      value={draft}
      onBlur={validate}
      onChange={(event) => {
        setDraft(event.target.value);
        if (error) setError('');
      }}
    />
    {error ? <Form.ErrorList className="mt-1" errors={[error]} /> : null}
  </div>;
});
