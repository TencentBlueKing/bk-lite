import { describe, expect, it } from 'vitest';

import { shouldNotifyTreeNodeSelect } from '../selectionNotify';

describe('shouldNotifyTreeNodeSelect', () => {
  it('首次选中节点时通知父页面', () => {
    expect(shouldNotifyTreeNodeSelect('', '22')).toBe(true);
  });

  it('用户改选另一节点时通知父页面', () => {
    expect(shouldNotifyTreeNodeSelect('22', '35')).toBe(true);
  });

  it('URL 回写同一节点时不再通知，避免父页面 abort 进行中的插件列表请求', () => {
    expect(shouldNotifyTreeNodeSelect('35', '35')).toBe(false);
    expect(shouldNotifyTreeNodeSelect('35', 35)).toBe(false);
  });

  it('浏览器后退到上一节点时仍要通知', () => {
    expect(shouldNotifyTreeNodeSelect('35', '22')).toBe(true);
  });

  it('空 key 不通知', () => {
    expect(shouldNotifyTreeNodeSelect('35', '')).toBe(false);
    expect(shouldNotifyTreeNodeSelect('35', null)).toBe(false);
  });
});
