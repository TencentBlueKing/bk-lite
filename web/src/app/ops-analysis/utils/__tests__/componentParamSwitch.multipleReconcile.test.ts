import { describe, expect, test } from 'vitest';
import {
  reconcileComponentParamValue,
  reconcileComponentSwitchSelection,
  reconcileComponentSwitchValue,
  resolveComponentSwitchRuntime,
  sameParamValue,
  sanitizeComponentSwitchParams,
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

  test('标量失效时清空，不自动选中第一项', () => {
    expect(reconcileComponentParamValue('2', OPTIONS)).toBe('2');
    expect(reconcileComponentParamValue('missing', OPTIONS)).toBeNull();
    expect(reconcileComponentSwitchValue('missing', OPTIONS)).toBeNull();
    expect(reconcileComponentSwitchValue('1', [])).toBeNull();
  });

  test('内容相同的参数值视为没变，避免空数组再写进表单', () => {
    expect(sameParamValue([], [])).toBe(true);
    expect(sameParamValue(['12'], ['12'])).toBe(true);
    expect(sameParamValue(['12'], [])).toBe(false);
    expect(sameParamValue('12', '12')).toBe(true);
    expect(sameParamValue(null, null)).toBe(true);
  });

  test('选项还没回来时保留现值，已经是空列表时清空失效值', () => {
    expect(reconcileComponentParamValue('saved', undefined)).toBe('saved');
    expect(reconcileComponentParamValue(['saved'], undefined)).toEqual(['saved']);
    expect(reconcileComponentParamValue('saved', [])).toBeNull();
    expect(reconcileComponentParamValue(['saved', 'kept'], [])).toEqual([]);
    expect(reconcileComponentParamValue(null, [])).toBeNull();
  });

  test('组件内切换的多选必须整组都在选项里，否则不发请求', () => {
    expect(reconcileComponentSwitchSelection(['1', '2'], OPTIONS, true)).toEqual(['1', '2']);
    expect(reconcileComponentSwitchSelection(['2', '9'], OPTIONS, true)).toBeNull();
    const param: ParamItem = {
      name: 'metric',
      alias_name: '指标',
      type: 'string',
      filterType: 'params',
      value: ['1', '2'],
      inputConfig: {
        control: 'select',
        multiple: true,
        componentSwitch: true,
        optionsSource: { type: 'static', staticItems: OPTIONS },
      },
    };
    expect(resolveComponentSwitchRuntime('line', param, OPTIONS, ['1', '2'])).toEqual({
      value: ['1', '2'],
      params: { metric: ['1', '2'] },
    });
    expect(resolveComponentSwitchRuntime('line', param, OPTIONS, [])).toEqual({
      value: undefined,
      params: {},
    });
    expect(resolveComponentSwitchRuntime('text', param, OPTIONS, ['1'])).toEqual({
      value: undefined,
      params: {},
    });
  });

  test('不支持的图去掉组件内切换但保留多选，一张卡只留第一个', () => {
    const switched = (name: string): ParamItem => ({
      name,
      alias_name: name,
      type: 'string',
      filterType: 'params',
      value: '1',
      inputConfig: {
        control: 'select',
        multiple: true,
        componentSwitch: true,
        optionsSource: { type: 'static', staticItems: OPTIONS },
      },
    });
    const unsupported = sanitizeComponentSwitchParams('room3D', [switched('room')]);
    expect(unsupported.changed).toBe(true);
    expect(unsupported.warnings.map((warning) => warning.code)).toEqual([
      'component_switch_unsupported_chart',
    ]);
    expect(unsupported.params[0]?.inputConfig).toMatchObject({
      control: 'select',
      multiple: true,
    });
    expect(unsupported.params[0]?.inputConfig).not.toHaveProperty('componentSwitch');

    const extras = sanitizeComponentSwitchParams('line', [switched('first'), switched('second')]);
    expect(extras.params.map((param) => (
      param.inputConfig && 'componentSwitch' in param.inputConfig
        ? param.inputConfig.componentSwitch
        : undefined
    ))).toEqual([true, undefined]);
    expect(extras.warnings.map((warning) => warning.code)).toEqual([
      'component_switch_extra_dropped',
    ]);
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
