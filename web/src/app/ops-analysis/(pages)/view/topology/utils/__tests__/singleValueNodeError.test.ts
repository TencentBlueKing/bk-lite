import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import {
  clearSingleValueFetchError,
  showSingleValueFetchError,
} from '@/app/ops-analysis/(pages)/view/topology/utils/singleValueNodeError';

const createMockNode = () => {
  let data: Record<string, unknown> = { name: 'node-a' };
  const attrs: Record<string, Record<string, unknown>> = {
    label: { display: 'block', fontSize: 16 },
    errorIcon: { display: 'none' },
  };

  return {
    getData: () => data,
    setData: (next: Record<string, unknown>) => {
      data = { ...data, ...next };
    },
    getAttrByPath: (path: string) => {
      const [selector, key] = path.split('/');
      return attrs[selector]?.[key];
    },
    setAttrByPath: (path: string, value: unknown) => {
      const [selector, key] = path.split('/');
      attrs[selector] = {
        ...attrs[selector],
        [key]: value,
      };
    },
    attrs,
  };
};

describe('singleValueNodeError', () => {
  it('stores fetch error state and shows the warning icon', () => {
    const node = createMockNode();

    showSingleValueFetchError(node as never, '未找到可用命名空间');

    assert.equal(node.getData().hasError, true);
    assert.equal(node.getData().fetchError, true);
    assert.equal(node.getData().errorMessage, '未找到可用命名空间');
    assert.equal(node.attrs.label.display, 'none');
    assert.equal(node.attrs.errorIcon.display, 'block');
  });

  it('clears fetch error state and restores the value label', () => {
    const node = createMockNode();
    showSingleValueFetchError(node as never, '未找到可用命名空间');

    clearSingleValueFetchError(node as never);

    assert.equal(node.getData().hasError, false);
    assert.equal(node.getData().fetchError, false);
    assert.equal(node.getData().errorMessage, undefined);
    assert.equal(node.attrs.label.display, 'block');
    assert.equal(node.attrs.errorIcon.display, 'none');
  });
});
