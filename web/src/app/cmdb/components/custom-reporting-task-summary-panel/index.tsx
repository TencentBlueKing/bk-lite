'use client';

import dayjs from 'dayjs';
import CustomReportingCleanupStrategyValue from '@/app/cmdb/components/custom-reporting-cleanup-strategy-value';
import CustomReportingIdentityKeyGroup from '@/app/cmdb/components/custom-reporting-identity-key-group';
import CustomReportingModeBadge from '@/app/cmdb/components/custom-reporting-mode-badge';
import CustomReportingTargetModelValue from '@/app/cmdb/components/custom-reporting-target-model-value';
import DetailListPanel from '@/components/detail-list-panel';
import TagCapsuleGroup from '@/components/tag-capsule-group';
import { useTranslation } from '@/utils/i18n';
import type {
  CustomReportingTaskSummaryLike,
} from '@/app/cmdb/components/custom-reporting-shared/types';

export interface CustomReportingTaskSummaryPanelProps {
  task: CustomReportingTaskSummaryLike;
  teamLabels?: string[];
  variant?: 'compact' | 'detail';
}

const CustomReportingTaskSummaryPanel = ({
  task,
  teamLabels = [],
  variant = 'detail',
}: CustomReportingTaskSummaryPanelProps) => {
  const { t } = useTranslation();

  const detailItems = [
    {
      label: t('name'),
      value: task.name,
      copyable: false,
    },
    {
      label: t('CustomReporting.mode'),
      displayValue: <CustomReportingModeBadge mode={task.config?.mode} />,
      copyable: false,
    },
    {
      label: t('CustomReporting.targetModel'),
      displayValue: <CustomReportingTargetModelValue config={task.config} />,
      copyable: false,
    },
  ];

  const items =
    variant === 'compact'
      ? detailItems
      : [
        ...detailItems,
        {
          label: t('CustomReporting.identityKeys'),
          displayValue: (
              <CustomReportingIdentityKeyGroup
                keys={
                  task.config?.quick_model?.identity_keys ||
                  task.config?.identity_keys ||
                  []
                }
              />
          ),
          copyable: false,
        },
        {
          label: t('CustomReporting.teamScope'),
          displayValue: (
              <TagCapsuleGroup value={teamLabels} maxVisible={3} compact />
          ),
          copyable: false,
        },
        {
          label: t('CustomReporting.cleanupStrategy'),
          displayValue: (
              <CustomReportingCleanupStrategyValue
                strategy={task.config?.cleanup_strategy}
              />
          ),
          copyable: false,
        },
        {
          label: t('CustomReporting.lastReportedAt'),
          value: task.last_reported_at
            ? dayjs(task.last_reported_at).format('YYYY-MM-DD HH:mm:ss')
            : '--',
          copyable: false,
        },
        {
          label: t('updateTime'),
          value: dayjs(task.updated_at).format('YYYY-MM-DD HH:mm:ss'),
          copyable: false,
        },
      ];

  return (
    <DetailListPanel labelWidthClassName="w-32" items={items} />
  );
};

export default CustomReportingTaskSummaryPanel;
