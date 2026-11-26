'use client';

import { Button, Input, message } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import type { FormChoice } from '../types';

interface Props {
  options: FormChoice[];
  tree: boolean;
  onChange: (options: FormChoice[]) => void;
}

export function SubformOptions({ options, tree, onChange }: Props) {
  const values = new Set<string>();
  function collect(choices: FormChoice[]) {
    for (const choice of choices) {
      values.add(String(choice.value));
      if (choice.children) collect(choice.children);
    }
  }
  collect(options);
  function newChoice(): FormChoice {
    let n = 1;
    while (values.has(String(n))) n++;
    return { label: '选项' + n, value: String(n) };
  }
  function rows(items: FormChoice[], update: Props['onChange']) {
    return items.map((item, index) => {
      const patch = (next: Partial<FormChoice>) => update(items.map((entry, i) => i === index ? { ...entry, ...next } : entry));
      return <div key={item.value} className="flex flex-col gap-1">
        <div className="flex items-center gap-1">
          <Input aria-label="选项名称" value={item.label} onChange={e => patch({ label: e.target.value })} />
          <Input aria-label="选项值" defaultValue={item.value} onBlur={e => {
            const value = e.target.value.trim();
            if (value === String(item.value)) return;
            if (!value || values.has(value)) {
              e.target.value = String(item.value);
              message.warning('选项值不能为空或重复');
              return;
            }
            patch({ value });
          }} />
          {tree && <Button aria-label={'添加子选项 ' + item.label} icon={<PlusOutlined />} onClick={() => patch({ children: [...(item.children || []), newChoice()] })} />}
          <Button aria-label={'删除选项 ' + item.label} icon={<DeleteOutlined />} onClick={() => update(items.filter((_, i) => i !== index))} />
        </div>
        {!!item.children?.length && <div className="ml-3 flex flex-col gap-1 border-l pl-2">
          {rows(item.children, children => patch({ children }))}
        </div>}
      </div>;
    });
  }
  return <div className="flex flex-col gap-2">
    <span className="text-xs font-medium">自定义选项</span>
    {rows(options, onChange)}
    <Button onClick={() => onChange([...options, newChoice()])}>添加选项</Button>
  </div>;
}
