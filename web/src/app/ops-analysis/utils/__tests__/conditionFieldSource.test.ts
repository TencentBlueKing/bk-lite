import { describe, expect, it } from 'vitest';
import {
  conditionFieldFromDraft,
  conditionFieldFromSourceRow,
  draftFromConditionField,
  legacyDynamicConditionSource,
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

  it('round-trips a handwritten field and keeps query object limits', () => {
    const field = presentConditionField({
      value: 'status',
      label: '状态',
      valueType: 'enum',
      query_objects: ['alert'],
      options: [{ label: '待响应', value: 'pending', query_objects: ['alert'] }],
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

  it('shows an old follow-model source as a normal datasource config', () => {
    expect(legacyDynamicConditionSource({
      kind: 'modelAttrs',
      modelParam: 'model_id',
    })).toEqual({
      sourceRef: { type: 'rest_api', value: 'cmdb/list_cmdb_attr_options' },
      valueField: 'attr_id',
      labelField: 'attr_name',
      queryParams: { model_id: { ref: 'model_id' } },
    });
    expect(legacyDynamicConditionSource({
      kind: 'endModelAttrs',
      startModelParam: 'start_model_id',
      associationParam: 'model_asst_id',
    })?.queryParams).toEqual({
      start_model_id: { ref: 'start_model_id' },
      model_asst_id: { ref: 'model_asst_id' },
    });
  });
});
