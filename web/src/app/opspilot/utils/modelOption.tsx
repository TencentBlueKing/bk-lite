import type { ReactNode } from 'react';

interface ModelOptionLike {
  name: string;
  vendor_name?: string | null;
}

interface SelectableLlmModel {
  enabled?: boolean;
  vendor_enabled?: boolean;
}

export const selectableLlmModels = <T extends SelectableLlmModel>(models: T[]): T[] => {
  return models.filter((model) => model.enabled !== false && model.vendor_enabled !== false);
};

export interface BoundModelHint {
  id: number;
  name?: string;
  vendor_name?: string | null;
}

export interface LlmModelChoice<T extends { id: number; name: string }> {
  model: T;
  disabled: boolean;
}

const boundModelId = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isInteger(value) && value > 0) {
    return value;
  }
  if (typeof value === 'string' && /^[1-9]\d*$/.test(value)) {
    return Number(value);
  }
  return null;
};

export const withBoundUnavailableModels = <T extends { id: number; name: string; vendor_name?: string | null }>(
  models: readonly T[],
  current: unknown,
  hints: readonly BoundModelHint[] = [],
): LlmModelChoice<T>[] => {
  const choices: LlmModelChoice<T>[] = models.map((model) => ({ model, disabled: false }));
  const present = new Set(models.map((model) => model.id));
  const values = Array.isArray(current) ? current : [current];
  values.forEach((value) => {
    const id = boundModelId(value);
    if (id == null || present.has(id)) {
      return;
    }
    present.add(id);
    const hint = hints.find((item) => item.id === id);
    const name = hint?.name?.trim() || String(id);
    choices.push({
      model: { id, name, vendor_name: hint?.vendor_name ?? null } as T,
      disabled: true,
    });
  });
  return choices;
};

export const getModelOptionText = (model: ModelOptionLike, unavailableMark?: string): string => {
  const base = model.vendor_name ? `${model.name} (${model.vendor_name})` : model.name;
  return unavailableMark ? `${base}（${unavailableMark}）` : base;
};

export const renderModelOptionLabel = (model: ModelOptionLike, unavailableMark?: string): ReactNode => {
  return (
    <>
      <span>{model.name}</span>
      {model.vendor_name ? <span style={{ color: 'var(--color-text-3)' }}> ({model.vendor_name})</span> : null}
      {unavailableMark ? <span style={{ color: 'var(--color-text-3)' }}>（{unavailableMark}）</span> : null}
    </>
  );
};

export const filterModelOption = (input: string, option?: { title?: string | number | null }): boolean => {
  return String(option?.title || '').toLowerCase().includes(input.toLowerCase());
};
