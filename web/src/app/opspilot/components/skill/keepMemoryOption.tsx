'use client';

import React from 'react';
import { Checkbox } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { shouldOfferKeepMemory } from '@/app/opspilot/utils/skillMemoryUi';

interface KeepMemoryOptionProps {
  pendingRounds?: number | null;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

const KeepMemoryOption: React.FC<KeepMemoryOptionProps> = ({ pendingRounds, checked, onChange }) => {
  const { t } = useTranslation();
  if (!shouldOfferKeepMemory(pendingRounds)) {
    return null;
  }
  return (
    <Checkbox className="mt-2" checked={checked} onChange={(event) => onChange(event.target.checked)}>
      {t('skill.chat.keepMemory')}
    </Checkbox>
  );
};

export default KeepMemoryOption;
