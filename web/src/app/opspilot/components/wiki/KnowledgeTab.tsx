'use client';

import React, { useState } from 'react';
import { ApartmentOutlined, FileTextOutlined } from '@ant-design/icons';
import { Tabs } from 'antd';
import { useTranslation } from '@/utils/i18n';
import PageTab from './PageTab';
import GraphTab from './GraphTab';

// 知识工作区(spec 4.3):一个一级工作区,内含两个二级视图——知识页面 + 关系图
const KnowledgeTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const [view, setView] = useState<'page' | 'graph'>('page');

  return (
    // 撑满内容区:图谱视图据此 flex 填充满高,避免固定高 calc 撑出纵向滚动条
    <div className="h-full min-h-0">
      <Tabs
        activeKey={view}
        onChange={(key) => setView(key as 'page' | 'graph')}
        destroyOnHidden
        className="h-full [&_.ant-tabs-content-holder]:flex-1 [&_.ant-tabs-content-holder]:min-h-0 [&_.ant-tabs-content]:h-full [&_.ant-tabs-tabpane]:h-full [&_.ant-tabs-nav]:mb-3"
        items={[
          {
            key: 'page',
            label: (
              <span>
                <FileTextOutlined className="mr-1.5" />
                {t('wiki.page')}
              </span>
            ),
            children: <PageTab kbId={kbId} />,
          },
          {
            key: 'graph',
            label: (
              <span>
                <ApartmentOutlined className="mr-1.5" />
                {t('wiki.graph')}
              </span>
            ),
            children: <GraphTab kbId={kbId} />,
          },
        ]}
      />
    </div>
  );
};

export default KnowledgeTab;