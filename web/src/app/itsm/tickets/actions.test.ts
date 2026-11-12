import { describe, expect, it } from 'vitest';
import { actionOf } from './actions';

describe('节点动作按类型判断', () => {
  it('设计器生成的审批节点使用审批动作', () => {
    expect(actionOf('approval')).toBe('approve');
  });
  it('处理和提单节点使用提交动作', () => {
    expect(actionOf('handle')).toBe('submit');
    expect(actionOf('submit')).toBe('submit');
  });
});
