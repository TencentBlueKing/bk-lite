'use client';

import MatchRule, { type MatchRuleProps } from '../../components/matchRule';

export default function ScenarioMatchRule(props: MatchRuleProps) {
  return <MatchRule {...props} scope="correlation" />;
}
