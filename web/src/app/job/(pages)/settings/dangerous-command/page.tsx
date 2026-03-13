'use client';

import React from 'react';
import { useTranslation } from '@/utils/i18n';
import DangerousRulePage from '@/app/job/components/dangerous-rule-page';
import useJobApi from '@/app/job/api';

const DangerousCommandPage = () => {
  const { t } = useTranslation();
  const {
    getDangerousRuleList,
    createDangerousRule,
    updateDangerousRule,
    patchDangerousRule,
    deleteDangerousRule,
  } = useJobApi();

  return (
    <DangerousRulePage
      title={t('job.dangerousCommand')}
      description={t('job.dangerousCommandDesc')}
      addModalTitle={t('job.addDangerousCommand')}
      editModalTitle={t('job.editDangerousCommand')}
      patternLabel={t('job.matchPatternCommand')}
      patternPlaceholder={t('job.matchPatternPlaceholder')}
      patternHelp={t('job.matchPatternHelpCommand')}
      patternExamples={[
        t('job.matchPatternExample1'),
        t('job.matchPatternExample2'),
        t('job.matchPatternExample3'),
      ]}
      forbiddenLabel={t('job.forbiddenExecution')}
      confirmLabel={t('job.confirmExecution')}
      strategyHelp={t('job.handleStrategyHelpCommand')}
      ruleNamePlaceholder={t('job.ruleNamePlaceholder')}
      api={{
        getList: getDangerousRuleList,
        create: createDangerousRule,
        update: updateDangerousRule,
        patch: patchDangerousRule,
        remove: deleteDangerousRule,
      }}
    />
  );
};

export default DangerousCommandPage;
