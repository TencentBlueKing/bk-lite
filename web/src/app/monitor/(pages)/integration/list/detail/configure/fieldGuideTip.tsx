'use client';

import React from 'react';
import { useTranslation } from '@/utils/i18n';
import FieldGuideTip from '@/components/field-guide-tip';

interface MonitorFieldGuideTipProps {
  short?: string;
}

const MonitorFieldGuideTip: React.FC<MonitorFieldGuideTipProps> = ({
  short
}) => {
  const { t } = useTranslation();
  return (
    <FieldGuideTip
      short={short}
      title={t('monitor.integrations.fieldGuideTip')}
    />
  );
};

export default MonitorFieldGuideTip;
