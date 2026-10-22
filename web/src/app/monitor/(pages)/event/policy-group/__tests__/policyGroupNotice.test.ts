import { describe, expect, it } from 'vitest';
import { buildPolicyGroupNoticePayload, policyGroupListBadges } from '../policyGroupNotice';

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

describe('策略组列表缺口', () => {
  it('通知关闭或已经配好时不在名称旁罗列渠道和人员', () => {
    expect(policyGroupListBadges({ notice: false, noticeTypeIds: [], handlersUniform: true })).toEqual([]);
    expect(policyGroupListBadges({ notice: true, noticeTypeIds: [3], handlersUniform: true })).toEqual([]);
  });

  it('通知开着但没选方式时只标这个缺口', () => {
    expect(policyGroupListBadges({ notice: true, noticeTypeIds: [] })).toEqual(['未选通知方式']);
  });

  it('组内不一致时分别标出通知和处理人', () => {
    expect(
      policyGroupListBadges({
        notice: true,
        noticeUniform: false,
        noticeTypeIds: [3],
        handlersUniform: false,
      })
    ).toEqual(['通知不一致', '处理人不一致']);
  });
});
