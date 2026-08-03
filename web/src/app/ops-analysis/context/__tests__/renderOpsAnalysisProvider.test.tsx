import React, { useEffect } from 'react';
import { render, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  DashboardRenderOpsAnalysisProvider,
  useOpsAnalysis,
} from '@/app/ops-analysis/context/common';

const getDataSourceDetails = vi.fn().mockResolvedValue({
  items: [{ id: 17, name: 'scoped-source', groups: [999] }],
});

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({ getDataSourceDetails }),
}));

vi.mock('@/app/ops-analysis/api/namespace', () => ({
  useNamespaceApi: () => ({ getNamespaceList: vi.fn() }),
}));

vi.mock('@/app/ops-analysis/context/shareDataSource', () => ({
  useSharedDataSourceQuery: () => null,
}));

vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => {
    throw new Error('ordinary user context must not be read');
  },
}));

const Probe = ({ onDataSources }: { onDataSources: (value: unknown) => void }) => {
  const { loadCanvasDataSources, dataSources } = useOpsAnalysis();

  useEffect(() => {
    void loadCanvasDataSources([17]);
  }, [loadCanvasDataSources]);

  useEffect(() => {
    if (dataSources.length > 0) onDataSources(dataSources);
  }, [dataSources, onDataSources]);

  return null;
};

describe('DashboardRenderOpsAnalysisProvider', () => {
  it('uses backend-scoped authorization without ordinary user context', async () => {
    const onDataSources = vi.fn();

    render(
      <DashboardRenderOpsAnalysisProvider>
        <Probe onDataSources={onDataSources} />
      </DashboardRenderOpsAnalysisProvider>,
    );

    await waitFor(() => {
      expect(onDataSources).toHaveBeenCalledWith([
        expect.objectContaining({ id: 17, hasAuth: true }),
      ]);
    });
  });
});
