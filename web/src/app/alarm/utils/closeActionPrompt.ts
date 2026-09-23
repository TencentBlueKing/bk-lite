export interface CloseActionPromptRule {
  is_active?: boolean;
  auto_execute?: boolean;
  trigger_events?: string[];
  team?: Array<string | number>;
}

export interface CloseActionPromptAlert {
  team?: Array<string | number>;
}

export const shouldPromptActionOnClose = (
  rule: CloseActionPromptRule,
  alert?: CloseActionPromptAlert
): boolean => {
  if (rule.is_active === false) return false;
  if (rule.auto_execute !== false) return false;
  if (!rule.trigger_events?.includes('closed')) return false;

  const ruleTeams = (rule.team || []).map(String).filter(Boolean);
  if (!ruleTeams.length) return true;

  const alertTeams = new Set((alert?.team || []).map(String));
  return ruleTeams.some((teamId) => alertTeams.has(teamId));
};
