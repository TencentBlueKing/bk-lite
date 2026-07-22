'use client';

import React from 'react';
import { Button } from 'antd';
import { ReadOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { usePluginGuide } from './pluginContext';
import styles from './pluginGuidePanel.module.scss';

/** 配置区标题行右侧的「配置指南」入口。 */
const GuideEntryButton: React.FC = () => {
  const { t } = useTranslation();
  const { openGuide, hasGuide } = usePluginGuide();

  if (!hasGuide) {
    return null;
  }

  return (
    <Button
      size="small"
      className={styles.guideEntry}
      icon={<ReadOutlined />}
      onClick={openGuide}
    >
      {t('monitor.integrations.configGuide')}
    </Button>
  );
};

export default GuideEntryButton;
