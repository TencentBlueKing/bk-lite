'use client';

import React, { useState } from 'react';
import { Segmented } from 'antd';
import { useTranslation } from '@/utils/i18n';
import PageTab from './PageTab';
import GraphTab from './GraphTab';

// 知识工作区(spec 4.3):一个一级工作区,内含两个二级视图——知识页面 + 关系图
const KnowledgeTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const [view, setView] = useState<'page' | 'graph'>('page');
  return (
    <div>
      <Segmented
        className="mb-3"
        value={view}
        onChange={(v) => setView(v as 'page' | 'graph')}
        options={[
          { label: t('wiki.page'), value: 'page' },
          { label: t('wiki.graph'), value: 'graph' },
        ]}
      />
      {view === 'page' ? <PageTab kbId={kbId} /> : <GraphTab kbId={kbId} />}
    </div>
  );
};

export default KnowledgeTab;
