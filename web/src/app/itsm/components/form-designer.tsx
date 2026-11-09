'use client';

import { Button } from 'antd';
import { useState } from 'react';
import type { FormFieldSchema } from '../types';

const CONTROLS = ['input', 'number', 'select', 'user', 'cmdb', 'attachment'];

export function FormDesigner() {
  const [fields, setFields] = useState<FormFieldSchema[]>([]);
  return (
    <div className="grid grid-cols-3 gap-4">
      <div>
        {CONTROLS.map((type) => (
          <Button key={type} className="mb-2 block" onClick={() => setFields((current) => [...current, { key: `${type}_${current.length}`, type, label: type }])}>
            {type}
          </Button>
        ))}
      </div>
      <div>{fields.map((field) => <div key={field.key}>{field.label}</div>)}</div>
      <div>属性</div>
    </div>
  );
}
