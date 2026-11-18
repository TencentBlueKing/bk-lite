export const POLICY_GROUP_OTHER_ORG_HINT =
  '这台实例属于其他组织，策略组请切换到所属组织后修改';

export function isPolicyGroupMembershipReadOnly(
  membership: { read_only?: boolean } | null | undefined
): boolean {
  return membership?.read_only === true;
}

export function policyGroupMembershipLabel(
  membership: {
    group_name?: string | null;
    group_organization_name?: string | null;
  } | null | undefined
): string {
  const name = String(membership?.group_name || '').trim();
  if (!name) return '';
  const organization = String(membership?.group_organization_name || '').trim();
  if (!organization) return name;
  return `${name}（${organization}）`;
}
