import React, { useState, useEffect } from 'react';
import { XFlow, XFlowGraph, Grid, Snapline, Minimap } from '@antv/xflow';
import useApiClient from '@/utils/request';
import { InitNode } from './topoData';
import { Spin } from 'antd';
import topoStyle from './index.module.scss';
import { AssoTopoProps, TopoData } from '@/app/cmdb/types/assetData';

const Topo: React.FC<AssoTopoProps> = ({
  assoTypeList,
  modelList,
  modelId,
  instId,
}) => {
  const { get, isLoading } = useApiClient();
  const [topoData, setTopoData] = useState<TopoData>({});
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    if (isLoading) return;
    getTopoList();
  }, [modelId, instId, isLoading]);

  const getTopoList = async () => {
    setLoading(true);
    try {
      const data = await get(`/cmdb/api/instance/topo_search/${modelId}/${instId}/`);
      setTopoData(data);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Spin spinning={loading}>
      <div
        className={topoStyle.topo}
        style={{ height: 'calc(100vh - 160px)' }}
        id="container"
      >
        <XFlow>
          <XFlowGraph zoomable pannable minScale={0.05} maxScale={10} fitView />
          <Grid type="dot" options={{ color: '#ccc', thickness: 1 }} />
          <Snapline sharp />
          <Minimap
            width={200}
            height={120}
            style={{
              border: '1px solid var(--color-border-3)',
              bottom: '10px',
              right: '10px',
              position: 'absolute',
            }}
          />
          <InitNode
            modelId={modelId}
            instId={instId}
            topoData={topoData}
            assoTypeList={assoTypeList}
            modelList={modelList}
          />
        </XFlow>
      </div>
    </Spin>
  );
};

export default Topo;
