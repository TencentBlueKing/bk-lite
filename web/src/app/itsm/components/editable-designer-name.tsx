'use client';

import { EditOutlined } from '@ant-design/icons';
import { Input, message } from 'antd';
import { useRef, useState } from 'react';

interface Props {
  name: string;
  fallback: string;
  label: string;
  disabled?: boolean;
  maxLength?: number;
  onSave: (name: string) => Promise<void>;
}

export function EditableDesignerName({ name, fallback, label, disabled, maxLength = 128, onSave }: Props) {
  const [editName, setEditName] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const cancelRename = useRef(false);
  const rename = async () => {
    const next = editName?.trim();
    if (renaming) return;
    if (cancelRename.current || !next || next === name) {
      cancelRename.current = false;
      setEditName(null);
      return;
    }
    setRenaming(true);
    try {
      await onSave(next);
      setEditName(null);
    } catch (error) {
      message.error(error instanceof Error ? error.message : `${label}修改失败`);
    } finally {
      setRenaming(false);
    }
  };
  return editName === null ? (
    <button type="button" aria-label={`修改${label}`} title={name}
      className="inline-flex max-w-[min(50vw,28rem)] items-center gap-2 text-sm font-medium text-[var(--color-text-1)] hover:text-[var(--color-primary)]"
      disabled={disabled} onClick={() => setEditName(name)}>
      <span className="truncate">{name || fallback}</span>
      <EditOutlined />
    </button>
  ) : (
    <Input aria-label={label} autoFocus maxLength={maxLength} showCount value={editName} readOnly={renaming}
      style={{ width: 'min(50vw, 22rem)' }}
      onFocus={event => event.target.select()}
      onChange={event => setEditName(event.target.value)}
      onBlur={() => void rename()}
      onKeyDown={event => {
        if (event.nativeEvent.isComposing || renaming) return;
        if (event.key === 'Enter' || event.key === 'Escape') {
          event.preventDefault();
          cancelRename.current = event.key === 'Escape';
          event.currentTarget.blur();
        }
      }} />
  );
}
