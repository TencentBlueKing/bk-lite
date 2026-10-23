export interface PolicyGroupNoticePayloadInput {
  groupId: number;
  noticeEnabled: boolean;
  noticeType: string;
  noticeTypeIds: number[];
  noticeUsersRequired: boolean;
  noticeUserIds: string[];
  handlerIds: string[];
}

export interface PolicyGroupListBadgeInput {
  notice?: boolean;
  noticeUniform?: boolean;
  noticeTypeIds?: Array<string | number>;
  handlersUniform?: boolean;
}

/** 列表只标需要处理的缺口。渠道名和处理人名单在响应配置里看。 */
export const policyGroupListBadges = ({
  notice,
  noticeUniform = true,
  noticeTypeIds = [],
  handlersUniform = true,
}: PolicyGroupListBadgeInput): string[] => {
  const badges: string[] = [];
  if (noticeUniform === false) {
    badges.push('通知不一致');
  } else if (notice) {
    const ids = noticeTypeIds.map((item) => Number(item)).filter((item) => Number.isFinite(item));
    if (!ids.length) badges.push('未选通知方式');
  }
  if (handlersUniform === false) badges.push('处理人不一致');
  return badges;
};

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
