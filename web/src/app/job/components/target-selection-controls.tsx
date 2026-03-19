'use client';

import React from 'react';
import { Button, Radio } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { TargetSourceType } from './host-selection-modal';
import styles from './target-selection-controls.module.scss';

interface TargetSourceSelectorProps {
  value: TargetSourceType;
  onChange: (value: TargetSourceType) => void;
}

interface AddTargetHostButtonProps {
  count: number;
  onClick: () => void;
}

export function TargetSourceSelector({ value, onChange }: TargetSourceSelectorProps) {
  const { t } = useTranslation();

  return (
    <Radio.Group
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className={styles.targetSourceGroup}
    >
      <Radio value="target_manager">{t('job.targetManager')}</Radio>
      <Radio value="node_manager">{t('job.nodeManager')}</Radio>
    </Radio.Group>
  );
}

export function AddTargetHostButton({ count, onClick }: AddTargetHostButtonProps) {
  const { t } = useTranslation();

  return (
    <div className={styles.addTargetHostWrapper}>
      <Button
        type="dashed"
        icon={<PlusOutlined />}
        onClick={onClick}
        className={styles.addTargetHostButton}
      >
        {t('job.addTargetHost')}
      </Button>
      <span className={styles.addTargetHostMeta}>
        {t('job.selectedHosts').replace('{count}', String(count))}
      </span>
    </div>
  );
}
