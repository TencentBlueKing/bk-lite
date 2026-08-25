import { describe, expect, test } from 'vitest';
import {
  reconcileComponentParamValue,
  reconcileComponentSwitchValue,
} from '@/app/ops-analysis/utils/componentParamSwitch';
import { processDataSourceParams } from '@/app/ops-analysis/utils/widgetDataTransform';
import type { InputOption, ParamItem } from '@/app/ops-analysis/types/dataSource';

const OPTIONS: InputOption[] = [
  { label: '1', value: '1' },
  { label: '2', value: '2' },
  { label: '3', value: '3' },
];

describe('reconcileComponentParamValue multiple', () => {
  test('保留多选数组中仍存在于选项里的全部值，不得截成 options[0]', () => {
    expect(reconcileComponentParamValue(['1', '2'], OPTIONS)).toEqual(['1', '2']);
  });

  test('多选数组过滤已失效选项，空结果保持空数组', () => {
    expect(reconcileComponentParamValue(['9', '8'], OPTIONS)).toEqual([]);
    expect(reconcileComponentParamValue(['2', '9'], OPTIONS)).toEqual(['2']);
  });

  test('标量仍按组件切换同源规则回落到首项', () => {
    expect(reconcileComponentParamValue('2', OPTIONS)).toBe('2');
    expect(reconcileComponentParamValue('missing', OPTIONS)).toBe('1');
    expect(reconcileComponentSwitchValue('missing', OPTIONS)).toBe('1');
  });

  test('确认提交链路：多选查询参数经选项对齐后请求仍为完整数组', () => {
    const formValue = ['1', '2'];
    const reconciled = reconcileComponentParamValue(formValue, OPTIONS);
    const sourceParams: ParamItem[] = [
      {
        name: 'cheshi2',
        alias_name: '测试',
        type: 'string',
        filterType: 'params',
        value: reconciled,
        inputConfig: {
          control: 'select',
          multiple: true,
          optionsSource: {
            type: 'static',
            staticItems: OPTIONS,
          },
        },
      },
    ];

    expect(
      processDataSourceParams({
        sourceParams,
        userParams: { cheshi2: reconciled },
      }),
    ).toEqual({ cheshi2: ['1', '2'] });
  });
});
