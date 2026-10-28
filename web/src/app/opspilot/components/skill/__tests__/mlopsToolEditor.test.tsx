import React, { createRef } from 'react';
import { act, render, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import MlopsToolEditor, { MlopsToolEditorHandle, parseMlopsServingId } from '../mlopsToolEditor';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback || _key }),
}));

vi.mock('@/app/opspilot/api/skill', () => ({
  useSkillApi: () => ({
    fetchTimeseriesPredictServings: vi.fn().mockResolvedValue([{ id: 12, name: 'disk-forecast' }]),
  }),
}));

describe('parseMlopsServingId', () => {
  it('reads the single bound serving id', () => {
    expect(parseMlopsServingId([{ key: 'serving_ids', value: '[12]', type: 'string', isRequired: true }])).toBe(12);
  });

  it('returns null when the binding is empty', () => {
    expect(parseMlopsServingId([])).toBeNull();
  });

  it('saves the single selected serving as serving_ids', async () => {
    const onSave = vi.fn();
    const ref = createRef<MlopsToolEditorHandle>();
    render(
      <MlopsToolEditor
        ref={ref}
        initialKwargs={[{ key: 'serving_ids', value: '[12]', type: 'string', isRequired: true }]}
        onSave={onSave}
      />,
    );
    await waitFor(() => expect(ref.current).toBeTruthy());
    let saved = false;
    act(() => {
      saved = ref.current?.save() ?? false;
    });
    expect(saved).toBe(true);
    expect(onSave).toHaveBeenCalledWith([
      { key: 'serving_ids', value: '[12]', type: 'string', isRequired: true },
    ]);
  });
});
