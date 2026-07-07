'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Empty, Spin, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { WikiGraph } from '@/app/opspilot/types/wiki';
import GraphExplorer from '@/app/opspilot/components/wiki/GraphExplorer';

// 关系图谱:全幅图 + 浮动工具条/面板(过滤器、洞察、社区图例、缩放、全屏),信息以浮层 tip 形式呈现
const GraphTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchGraphAnalysis, rebuildRelations, scan } = useWikiApi();
  const [graph, setGraph] = useState<WikiGraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [creatingInsightChecks, setCreatingInsightChecks] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setGraph(await fetchGraphAnalysis(kbId));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  const titleOf = useMemo(() => {
    const map = new Map<number, string>();
    (graph?.nodes || []).forEach((n) => map.set(n.id, n.title));
    return (id: number) => map.get(id) || `#${id}`;
  }, [graph]);

  const handleRebuild = async () => {
    setRebuilding(true);
    try {
      await rebuildRelations(kbId);
      await load();
    } finally {
      setRebuilding(false);
    }
  };

  const handleCreateInsightChecks = async () => {
    setCreatingInsightChecks(true);
    try {
      const res = await scan(kbId);
      message.success(`${t('wiki.createInsightChecksDone')}: ${res.created}`);
      await load();
    } finally {
      setCreatingInsightChecks(false);
    }
  };

  if (!graph) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin spinning={loading}>
          <Empty />
        </Spin>
      </div>
    );
  }

  // height="100%":铺满父级 flex 容器,使图谱随内容区高度自适应,不再用固定 calc 撑出滚动条
  return (
    <div className="h-full">
      <GraphExplorer
        graph={graph}
        titleOf={titleOf}
        onRebuild={handleRebuild}
        rebuilding={rebuilding}
        onCreateInsightChecks={handleCreateInsightChecks}
        creatingInsightChecks={creatingInsightChecks}
        height="100%"
      />
    </div>
  );
};

export default GraphTab;
