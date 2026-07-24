'use client';

import React from 'react';
import { Drawer, List } from 'antd';
import { useTranslation } from '@/utils/i18n';

interface CommonIssuesDrawerProps {
  open: boolean;
  onClose: () => void;
}

const CommonIssuesDrawer: React.FC<CommonIssuesDrawerProps> = ({
  open,
  onClose,
}) => {
  const { t } = useTranslation();
  const issues = [
    t('monitor.integrations.k3s.issueRbac'),
    t('monitor.integrations.k3s.issueNats'),
    t('monitor.integrations.k3s.issueArchitecture'),
  ];
  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t('monitor.integrations.k3s.commonIssues')}
    >
      <List dataSource={issues} renderItem={(item) => <List.Item>{item}</List.Item>} />
    </Drawer>
  );
};

export default CommonIssuesDrawer;
