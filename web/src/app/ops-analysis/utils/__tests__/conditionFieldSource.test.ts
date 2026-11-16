import { describe, expect, it } from 'vitest';
import {
  conditionFieldFromDraft,
  conditionFieldFromSourceRow,
  draftFromConditionField,
  presentConditionField,
} from '@/app/ops-analysis/utils/conditionFieldSource';

describe('condition field source', () => {
  it('uses brought enum options and turns an option-less enum into an input', () => {
    expect(conditionFieldFromSourceRow({
      attr_id: 'status',
      attr_name: '状态',
      value_type: 'enum',
      options: [{ value: '1', label: '已上线' }],
    }, 'attr_id', 'attr_name')).toEqual({
      value: 'status',
      label: '状态',
      valueType: 'enum',
      options: [{ value: '1', label: '已上线' }],
    });
    expect(presentConditionField({
      value: 'source',
      label: '来源',
      valueType: 'enum',
    })).toEqual({
      value: 'source',
      label: '来源',
      valueType: 'string',
    });
    expect(conditionFieldFromSourceRow({
      attr_id: 'cpu',
      attr_name: '核数',
      value_type: 'number',
      options: [],
    }, 'attr_id', 'attr_name')?.valueType).toBe('number');
  });

  it('round-trips a handwritten enum field', () => {
    const field = presentConditionField({
      value: 'status',
      label: '状态',
      valueType: 'enum',
      options: [{ label: '待响应', value: 'pending' }],
    });
    const draft = draftFromConditionField(field);
    expect(draft.valueMode).toBe('options');
    expect(conditionFieldFromDraft(draft)).toEqual(field);
    expect(conditionFieldFromDraft({
      value: 'name',
      label: '名称',
      valueMode: 'input',
      options: [],
    })).toEqual({ value: 'name', label: '名称', valueType: 'string' });
  });
});
