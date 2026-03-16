'use client';

import React from 'react';
import { useTranslation } from '@/utils/i18n';
import DangerousRulePage from '@/app/job/components/dangerous-rule-page';
import useJobApi from '@/app/job/api';

const DangerousPathPage = () => {
  const { t } = useTranslation();
  const {
    getDangerousPathList,
    createDangerousPath,
    updateDangerousPath,
    patchDangerousPath,
    deleteDangerousPath,
  } = useJobApi();

  return (
    <DangerousRulePage
      title={t('job.dangerousPath')}
      description={t('job.dangerousPathDesc')}
      addModalTitle={t('job.addDangerousPath')}
      editModalTitle={t('job.editDangerousPath')}
      patternLabel={t('job.matchPatternPath')}
      patternPlaceholder={t('job.matchPatternPathPlaceholder')}
      patternHelp={t('job.matchPatternHelpPath')}
      patternExamples={[
        t('job.matchPatternPathExample1'),
        t('job.matchPatternPathExample2'),
        t('job.matchPatternPathExample3'),
        t('job.matchPatternPathExample4'),
      ]}
      forbiddenLabel={t('job.forbiddenDistribution')}
      confirmLabel={t('job.confirmExecution')}
      strategyHelp={t('job.handleStrategyHelpPath')}
      ruleNamePlaceholder={t('job.ruleNamePathPlaceholder')}
      api={{
        getList: getDangerousPathList,
        create: createDangerousPath,
        update: updateDangerousPath,
        patch: patchDangerousPath,
        remove: deleteDangerousPath,
      }}
    />
  );
};

export default DangerousPathPage;
