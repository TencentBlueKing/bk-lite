import { describe, expect, it } from 'vitest';
import {
  adjustableConstBindings,
  alignParamBindings,
  defaultBindingsFromScript,
  fieldBindingsIncomplete,
  TRIGGER_EVENT_FIELD,
} from '../actionParamBindings';

const script = [
  { name: 'pkg', label: '包', default: 'openssl' },
  { name: 'token', label: '令牌', default: '******' },
  { name: 'empty', label: '空' },
];

describe('defaultBindingsFromScript', () => {
  it('writes plaintext defaults as const and treats masked defaults as empty', () => {
    expect(defaultBindingsFromScript(script)).toEqual([
      { name: 'pkg', from: 'const', value: 'openssl', allow_adjust: false },
      { name: 'token', from: 'const', value: '', allow_adjust: false },
      { name: 'empty', from: 'const', value: '', allow_adjust: false },
    ]);
  });
});

describe('alignParamBindings', () => {
  it('adds new params, drops removed ones, and keeps existing bindings', () => {
    const existing = [
      { name: 'pkg', from: 'field' as const, value: 'title', allow_adjust: true },
      { name: 'gone', from: 'const' as const, value: 'old' },
    ];
    expect(
      alignParamBindings(
        [
          { name: 'pkg', default: 'openssl' },
          { name: 'new', default: 'n1' },
        ],
        existing
      )
    ).toEqual([
      { name: 'pkg', from: 'field', value: 'title', allow_adjust: false },
      { name: 'new', from: 'const', value: 'n1', allow_adjust: false },
    ]);
  });

  it('reload overwrites const values but keeps field mappings and allow_adjust', () => {
    const existing = [
      { name: 'pkg', from: 'const' as const, value: 'custom', allow_adjust: true },
      { name: 'title', from: 'field' as const, value: 'title' },
    ];
    expect(
      alignParamBindings(
        [
          { name: 'pkg', default: 'openssl' },
          { name: 'title', default: 'x' },
        ],
        existing,
        { reloadConstDefaults: true }
      )
    ).toEqual([
      { name: 'pkg', from: 'const', value: 'openssl', allow_adjust: true },
      { name: 'title', from: 'field', value: 'title', allow_adjust: false },
    ]);
  });
});

describe('adjustableConstBindings', () => {
  it('only returns const params with allow_adjust', () => {
    expect(
      adjustableConstBindings([
        { name: 'a', from: 'const', value: '1', allow_adjust: true },
        { name: 'b', from: 'const', value: '2' },
        { name: 'c', from: 'field', value: 'title', allow_adjust: true },
      ])
    ).toEqual([{ name: 'a', from: 'const', value: '1', allow_adjust: true }]);
  });
});

describe('fieldBindingsIncomplete', () => {
  it('is true when a field binding has no path', () => {
    expect(
      fieldBindingsIncomplete([{ name: 'a', from: 'field', value: '' }])
    ).toBe(true);
    expect(
      fieldBindingsIncomplete([{ name: 'a', from: 'const', value: '' }])
    ).toBe(false);
    expect(
      fieldBindingsIncomplete([{ name: 'a', from: 'field', value: TRIGGER_EVENT_FIELD }])
    ).toBe(false);
  });
});
