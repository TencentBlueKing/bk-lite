'use client';

import { Button, Input, Select } from 'antd';
import { useState } from 'react';
import type { ConditionGroup } from '../types';

interface ConditionBuilderProps {
  fields: string[];
  onChange: (value: ConditionGroup) => void;
}

export function ConditionBuilder({ fields, onChange }: ConditionBuilderProps) {
  const [field, setField] = useState(fields[0] || '');
  const [op, setOp] = useState('=');
  const [value, setValue] = useState('');
  const publish = () => onChange({ logic: 'and', items: [{ field, op, value }] });
  return (
    <div className="flex gap-2">
      <Select value={field} options={fields.map((item) => ({ label: item, value: item }))} onChange={setField} />
      <Select value={op} options={['=', '!=', '>', 'in'].map((item) => ({ label: item, value: item }))} onChange={setOp} />
      <Input value={value} onChange={(event) => setValue(event.target.value)} />
      <Button onClick={publish}>生成条件</Button>
    </div>
  );
}
