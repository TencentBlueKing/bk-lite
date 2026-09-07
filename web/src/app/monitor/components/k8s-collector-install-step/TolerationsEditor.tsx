'use client';

import React from 'react';
import { Button, Input, Select } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import {
  DEFAULT_K8S_DAEMONSET_TOLERATIONS,
  K8S_TOLERATION_EFFECTS,
  MAX_K8S_DAEMONSET_TOLERATIONS,
  isUnsetTolerations,
  normalizeEditorToleration,
  type K8sDaemonSetToleration,
  type K8sTolerationEffect,
} from './tolerations';

export interface K8sDaemonSetTolerationsEditorCopy {
  add: string;
  restoreDefault: string;
  keyPlaceholder: string;
  valuePlaceholder: string;
  emptyHint: string;
  defaultHint: string;
  effectNoSchedule: string;
  effectNoExecute: string;
}

interface K8sDaemonSetTolerationsEditorProps {
  value?: K8sDaemonSetToleration[] | null;
  onChange?: (next: K8sDaemonSetToleration[] | null) => void;
  copy: K8sDaemonSetTolerationsEditorCopy;
  disabled?: boolean;
}

const effectLabel = (
  effect: K8sTolerationEffect,
  copy: K8sDaemonSetTolerationsEditorCopy
) => (effect === 'NoExecute' ? copy.effectNoExecute : copy.effectNoSchedule);

const K8sDaemonSetTolerationsEditor: React.FC<
  K8sDaemonSetTolerationsEditorProps
> = ({ value, onChange, copy, disabled = false }) => {
  const unset = isUnsetTolerations(value);
  const rows = unset
    ? DEFAULT_K8S_DAEMONSET_TOLERATIONS
    : value.map((item) => normalizeEditorToleration(item));

  const emit = (next: K8sDaemonSetToleration[] | null) => {
    onChange?.(next);
  };

  const commitRows = (nextRows: K8sDaemonSetToleration[]) => {
    emit(nextRows.map((item) => normalizeEditorToleration(item)));
  };

  const updateRow = (
    index: number,
    patch: Partial<K8sDaemonSetToleration>
  ) => {
    const next = rows.map((row, rowIndex) =>
      rowIndex === index ? { ...row, ...patch } : row
    );
    commitRows(next);
  };

  const removeRow = (index: number) => {
    commitRows(rows.filter((_, rowIndex) => rowIndex !== index));
  };

  const addRow = () => {
    if (rows.length >= MAX_K8S_DAEMONSET_TOLERATIONS) {
      return;
    }
    commitRows([...rows, { key: '', effect: 'NoSchedule' }]);
  };

  return (
    <div className="w-full max-w-[720px] overflow-hidden rounded-md border border-[var(--color-border)] bg-[var(--color-bg)]">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 py-2">
        <div className="min-w-0 text-[12px] leading-[18px] text-[var(--color-text-3)]">
          {unset ? copy.defaultHint : rows.length === 0 ? copy.emptyHint : null}
        </div>
        <Button
          type="link"
          size="small"
          className="!px-0"
          disabled={disabled || unset}
          onClick={() => emit(null)}
        >
          {copy.restoreDefault}
        </Button>
      </div>
      <div className="space-y-2 px-3 py-2.5">
        {rows.length === 0 ? (
          <div className="px-1 py-2 text-[12px] leading-[18px] text-[var(--color-text-3)]">
            {copy.emptyHint}
          </div>
        ) : (
          rows.map((row, index) => (
            <div
              key={`toleration-${index}`}
              className="grid grid-cols-[minmax(0,1.4fr)_120px_minmax(0,1fr)_28px] items-start gap-2"
            >
              <Input
                value={row.key}
                disabled={disabled}
                placeholder={copy.keyPlaceholder}
                className="w-full"
                onChange={(event) =>
                  updateRow(index, { key: event.target.value })
                }
              />
              <Select
                value={row.effect}
                disabled={disabled}
                className="w-full"
                options={K8S_TOLERATION_EFFECTS.map((effect) => ({
                  value: effect,
                  label: effectLabel(effect, copy),
                }))}
                onChange={(effect: K8sTolerationEffect) =>
                  updateRow(index, { effect })
                }
              />
              <Input
                value={row.value ?? ''}
                disabled={disabled}
                placeholder={copy.valuePlaceholder}
                className="w-full"
                onChange={(event) =>
                  updateRow(index, { value: event.target.value })
                }
              />
              <button
                type="button"
                disabled={disabled}
                aria-label="remove"
                className="mt-[6px] inline-flex h-5 w-5 cursor-pointer items-center justify-center rounded text-[var(--color-text-3)] transition-colors duration-150 hover:bg-[var(--color-fill-2)] hover:text-[var(--color-fail)] disabled:cursor-not-allowed disabled:opacity-40"
                onClick={() => removeRow(index)}
              >
                <MinusCircleOutlined />
              </button>
            </div>
          ))
        )}
        <Button
          type="link"
          size="small"
          icon={<PlusOutlined />}
          className="!px-0"
          disabled={disabled || rows.length >= MAX_K8S_DAEMONSET_TOLERATIONS}
          onClick={addRow}
        >
          {copy.add}
        </Button>
      </div>
    </div>
  );
};

export default K8sDaemonSetTolerationsEditor;
