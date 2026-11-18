export function candidateBelongsToOtherOrganization(
  organization: ReadonlyArray<string | number> | null | undefined,
  currentTeam: string | number | null | undefined
): boolean {
  const team = String(currentTeam ?? '').trim();
  if (!team) return false;
  const organizations = Array.isArray(organization) ? organization : [];
  return !organizations.some((item) => String(item).trim() === team);
}

export function joinCandidateCheckboxDisabled(input: {
  belongsToOtherOrganization: boolean;
  joinedHere: boolean;
}): boolean {
  return input.belongsToOtherOrganization || input.joinedHere;
}

export function joinCandidateGroupLabel(input: {
  belongsToOtherOrganization: boolean;
  policyGroupName?: string | null;
  joinedHere: boolean;
}): { kind: 'joined-here' | 'other-empty' | 'other-readonly' | 'empty' | 'named'; text: string } {
  if (input.belongsToOtherOrganization) {
    const name = String(input.policyGroupName || '').trim();
    if (name) return { kind: 'other-readonly', text: `已在 ${name}（只读）` };
    return { kind: 'other-empty', text: '属于其他组织' };
  }
  if (input.joinedHere) return { kind: 'joined-here', text: '已在组' };
  const name = String(input.policyGroupName || '').trim();
  if (!name) return { kind: 'empty', text: '未加入' };
  return { kind: 'named', text: `已在 ${name}` };
}
