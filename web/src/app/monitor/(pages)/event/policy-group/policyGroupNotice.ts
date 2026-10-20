export interface PolicyGroupNoticePayloadInput {
  groupId: number;
  noticeEnabled: boolean;
  noticeType: string;
  noticeTypeIds: number[];
  noticeUsersRequired: boolean;
  noticeUserIds: string[];
  handlerIds: string[];
}

/** 处理人与通知开关无关；关闭通知只清通知字段。 */
export const buildPolicyGroupNoticePayload = ({
  groupId,
  noticeEnabled,
  noticeType,
  noticeTypeIds,
  noticeUsersRequired,
  noticeUserIds,
  handlerIds,
}: PolicyGroupNoticePayloadInput) => ({
  group_id: groupId,
  notice: noticeEnabled,
  notice_type: noticeEnabled ? noticeType : '',
  notice_type_ids: noticeEnabled ? noticeTypeIds : [],
  notice_users: noticeEnabled && noticeUsersRequired ? noticeUserIds : [],
  handlers: handlerIds,
});
