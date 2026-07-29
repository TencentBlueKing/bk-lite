'use client';

import AlarmMatchRule, {
  type AlarmMatchRuleProps,
} from '@/app/alarm/components/alarm-match-rule';
import { useSourceApi } from '@/app/alarm/api/integration';
import { useCommon } from '@/app/alarm/context/common';

type AlarmMatchRuleRuntimeProps = Omit<
  AlarmMatchRuleProps,
  'levelOptionsOverride' | 'loadSourceOptions'
>;

const AlarmMatchRuleRuntime = ({
  levelType = 'event',
  sourceOptions,
  ...props
}: AlarmMatchRuleRuntimeProps) => {
  const { getAlertSources } = useSourceApi();
  const { levelMeta } = useCommon();

  return (
    <AlarmMatchRule
      {...props}
      levelType={levelType}
      sourceOptions={sourceOptions}
      levelOptionsOverride={levelMeta[levelType]?.list || []}
      loadSourceOptions={sourceOptions ? undefined : getAlertSources}
    />
  );
};

export default AlarmMatchRuleRuntime;
