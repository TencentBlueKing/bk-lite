'use client';

import type { TimePickerProps, TreeSelectProps } from 'antd';
import { Checkbox, DatePicker, Input, InputNumber, Radio, Select, TreeSelect } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import AIEditor from '@/app/opspilot/components/ai-editor';
import type { FormFieldSchema } from '../types';
import { UserSelector } from './user-selector';

function RichTextField({
  disabled,
  value,
  onChange,
  placeholder,
}: {
  disabled: boolean;
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
}) {
  if (disabled) {
    return <div className="whitespace-pre-wrap">{value || ''}</div>;
  }
  return (
    <div className="h-64">
      <AIEditor placeholder={placeholder} value={value} onChange={onChange} />
    </div>
  );
}

const DATE_TYPES = new Set(['date', 'time', 'datetime', 'dateRange']);

const asDayjs = (value: unknown, timeOnly = false): Dayjs | null => {
  if (value == null || value === '') {
    return null;
  }
  if (dayjs.isDayjs(value)) {
    return value;
  }
  const parsed = timeOnly && typeof value === 'string' && /^\d{2}:\d{2}(:\d{2})?$/.test(value)
    ? dayjs('2000-01-01T' + value) : dayjs(value as string | number | Date);
  return parsed.isValid() ? parsed : null;
};

const pickerValue = (field: FormFieldSchema, value: unknown) => {
  if (field.type === 'dateRange') {
    return Array.isArray(value) ? value.map(item => asDayjs(item)) : null;
  }
  return asDayjs(value, field.type === 'time');
};

const storedValue = (field: FormFieldSchema, value: unknown) => {
  if (field.type === 'dateRange') {
    return Array.isArray(value)
      ? value.map((item) => (dayjs.isDayjs(item) ? item.format('YYYY-MM-DD') : item))
      : value;
  }
  if (!dayjs.isDayjs(value)) {
    return value;
  }
  if (field.type === 'time') {
    return value.format('HH:mm:ss');
  }
  if (field.type === 'datetime') {
    return value.format('YYYY-MM-DD HH:mm:ss');
  }
  return value.format('YYYY-MM-DD');
};

export const dateItemProps = (field: FormFieldSchema) => (
  DATE_TYPES.has(field.type)
    ? {
      getValueProps: (value: unknown) => ({ value: pickerValue(field, value) }),
      normalize: (value: unknown) => storedValue(field, value),
    }
    : {}
);

const numericProp = (value: unknown) =>
  value != null && value !== '' && Number.isFinite(Number(value)) ? Number(value) : undefined;

interface TreeOption {
  label: string;
  value: string | number;
  children?: TreeOption[];
}

function cascadeNodes(options: TreeOption[], anyLevel: boolean, parent = ''): Array<TreeOption & { path: string; selectable: boolean }> {
  return options.map(option => {
    const path = parent ? parent + ' / ' + option.label : option.label;
    return {
      ...option, path, selectable: anyLevel || !option.children?.length,
      children: option.children && cascadeNodes(option.children, anyLevel, path),
    };
  });
}

function CascadeField({ field, treeData = field.source?.options || [], ...props }: Omit<TreeSelectProps, 'treeData'> & {
  field: FormFieldSchema;
  treeData?: TreeOption[];
}) {
  const nodes = cascadeNodes(treeData, Boolean(field.cascadeAnyLevel));
  return <TreeSelect {...props} treeData={nodes} treeNodeLabelProp={field.showCascadePath === false ? 'label' : 'path'}
    fieldNames={{ label: 'label', value: 'value', children: 'children' }} multiple={field.type === 'multiCascade'}
    showSearch treeNodeFilterProp="label" placeholder={field.placeholder || '请选择'} />;
}

export function basicFieldControl(field: FormFieldSchema, disabled: boolean) {
  if (field.type === 'number') {
    return <InputNumber className="w-full" disabled={disabled} placeholder={field.placeholder} min={numericProp(field.props?.min)} max={numericProp(field.props?.max)} precision={numericProp(field.props?.precision)} />;
  }
  if (field.type === 'textarea') {
    return <Input.TextArea disabled={disabled} rows={field.rows} placeholder={field.placeholder} />;
  }
  if (field.type === 'radio') {
    return <Radio.Group className={field.optionLayout === 'vertical' ? 'flex flex-col gap-1' : ''} disabled={disabled} options={field.source?.options || []} />;
  }
  if (field.type === 'checkbox') {
    return <Checkbox.Group className={field.optionLayout === 'vertical' ? 'flex flex-col gap-1' : ''} disabled={disabled} options={field.source?.options || []} />;
  }
  if (field.type === 'date') {
    return <DatePicker className="w-full" disabled={disabled} />;
  }
  if (field.type === 'time') {
    const step = Number(field.props?.step);
    const minuteStep = Number.isInteger(step) && step >= 1 && step <= 59 ? step as TimePickerProps['minuteStep'] : undefined;
    return <DatePicker className="w-full" picker="time" minuteStep={minuteStep} disabled={disabled} />;
  }
  if (field.type === 'datetime') {
    return <DatePicker className="w-full" showTime disabled={disabled} />;
  }
  if (field.type === 'dateRange') {
    return <DatePicker.RangePicker className="w-full" disabled={disabled} />;
  }
  if (field.type === 'user' || field.type === 'multiUser') {
    return <UserSelector multiple={field.type === 'multiUser'} disabled={disabled} placeholder={field.placeholder || '搜索用户'} />;
  }
  if (field.type === 'cascade' || field.type === 'multiCascade') {
    return <CascadeField field={field} disabled={disabled} />;
  }
  if (field.type === 'select' || field.type === 'multiselect') {
    const multiple = field.type === 'multiselect';
    return <Select mode={multiple ? 'multiple' : undefined} disabled={disabled} options={field.source?.options || []} placeholder={field.placeholder || '请选择'} />;
  }
  if (field.type === 'richtext') {
    return <RichTextField disabled={disabled} placeholder={field.placeholder} />;
  }
  return <Input disabled={disabled} maxLength={numericProp(field.props?.maxLength)} placeholder={field.placeholder} />;
}
