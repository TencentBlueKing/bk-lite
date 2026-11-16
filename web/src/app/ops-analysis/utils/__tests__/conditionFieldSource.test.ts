import { describe, expect, it } from 'vitest';
import {
  conditionFieldFromDraft,
  conditionFieldFromSourceRow,
  draftFromConditionField,
  presentConditionField,
} from '@/app/ops-analysis/utils/conditionFieldSource';
import { operatorsForFieldType, reconcileConditionRows } from '@/app/ops-analysis/utils/conditionFilter';

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
    expect(conditionFieldFromSourceRow({
      attr_id: 'tag',
      attr_name: '标签',
      value_type: 'tag',
      options: [{ value: '数据中心:广州', label: '数据中心:广州' }],
    }, 'attr_id', 'attr_name')).toEqual({
      value: 'tag',
      label: '标签',
      valueType: 'tag',
      options: [{ value: '数据中心:广州', label: '数据中心:广州' }],
    });
    expect(presentConditionField({
      value: 'tag',
      label: '标签',
      valueType: 'tag',
    })).toEqual({
      value: 'tag',
      label: '标签',
      valueType: 'tag',
    });
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

  it('keeps tag operators aligned with text fields and leaves a saved equals unchanged', () => {
    expect(operatorsForFieldType('tag')).toEqual(operatorsForFieldType('string'));
    const fields = [{ value: 'tag', label: '标签', valueType: 'tag' as const }];
    expect(reconcileConditionRows({
      logic: 'AND',
      items: [{ field: 'tag', op: 'eq', value: '数据中心:广州,备用' }],
    }, fields)).toEqual({
      logic: 'AND',
      items: [{ field: 'tag', op: 'eq', value: '数据中心:广州,备用' }],
    });
  });
});
