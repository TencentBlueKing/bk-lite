import { describe, expect, it } from 'vitest';
import { HandledRequestError } from '@/utils/request';
import {
  getNotificationTemplateDeleteErrorKey,
  isNotificationTemplateDeleteDisabled,
} from '../notificationTemplateActions';

describe('通知模板组删除交互', () => {
  it('模板组存在分派引用时禁用删除', () => {
    expect(isNotificationTemplateDeleteDisabled({
      is_builtin: false,
      is_global: false,
      assignment_count: 1,
    })).toBe(true);
  });

  it('识别请求层包装后的引用冲突', () => {
    const error = new HandledRequestError('模板正在使用，不能删除', {
      status: 409,
      payload: { references: [{ source_type: 'escalation_task' }] },
    });

    expect(getNotificationTemplateDeleteErrorKey(error))
      .toBe('settings.notificationTemplate.inUse');
  });
});
