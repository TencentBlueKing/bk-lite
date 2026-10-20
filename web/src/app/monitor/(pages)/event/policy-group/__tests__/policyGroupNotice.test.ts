import { describe, expect, it } from 'vitest';
import { buildPolicyGroupNoticePayload } from '../policyGroupNotice';

describe('策略组通知与处理人', () => {
  it('关闭通知仍提交处理人，并清空通知人和通知方式', () => {
    expect(
      buildPolicyGroupNoticePayload({
        groupId: 4,
        noticeEnabled: false,
        noticeType: 'email',
        noticeTypeIds: [9],
        noticeUsersRequired: false,
        noticeUserIds: ['7'],
        handlerIds: ['7', '8'],
      })
    ).toEqual({
      group_id: 4,
      notice: false,
      notice_type: '',
      notice_type_ids: [],
      notice_users: [],
      handlers: ['7', '8'],
    });
  });

  it('需要通知人时同时提交通知人和处理人', () => {
    expect(
      buildPolicyGroupNoticePayload({
        groupId: 4,
        noticeEnabled: true,
        noticeType: 'email',
        noticeTypeIds: [9],
        noticeUsersRequired: true,
        noticeUserIds: ['7'],
        handlerIds: ['7'],
      })
    ).toMatchObject({
      notice: true,
      notice_type: 'email',
      notice_type_ids: [9],
      notice_users: ['7'],
      handlers: ['7'],
    });
  });

  it('不需要通知人时清空通知人，处理人仍提交', () => {
    expect(
      buildPolicyGroupNoticePayload({
        groupId: 4,
        noticeEnabled: true,
        noticeType: 'nats',
        noticeTypeIds: [3],
        noticeUsersRequired: false,
        noticeUserIds: ['7'],
        handlerIds: [],
      })
    ).toMatchObject({
      notice_users: [],
      handlers: [],
    });
  });
});
