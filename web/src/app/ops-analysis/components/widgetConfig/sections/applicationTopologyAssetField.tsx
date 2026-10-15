'use client';

import React from 'react';
import { Form, Input } from 'antd';
import { FilterBindingPanel } from '@/app/ops-analysis/components/unifiedFilter';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import { APPLICATION_TOPOLOGY_DEFAULT_DEPTH } from '@/app/ops-analysis/types/sceneWidget';
import { useTranslation } from '@/utils/i18n';
import {
  APPLICATION_TOPOLOGY_DEPTH_FILTER_ID,
  APPLICATION_TOPOLOGY_DEPTH_FILTER_KEY,
  APPLICATION_TOPOLOGY_DEPTH_FILTER_NAME,
  APPLICATION_TOPOLOGY_FILTER_ID,
  APPLICATION_TOPOLOGY_FILTER_KEY,
  APPLICATION_TOPOLOGY_FILTER_NAME,
} from '@/app/ops-analysis/utils/applicationTopologyCanvasFilter';

const SHIPPED_SYSTEM_NAMES = new Set([APPLICATION_TOPOLOGY_FILTER_NAME, '应用系统']);
const SHIPPED_DEPTH_NAMES = new Set([APPLICATION_TOPOLOGY_DEPTH_FILTER_NAME, '展开层级']);

const linkageName = (
  saved: UnifiedFilterDefinition | undefined,
  shippedNames: Set<string>,
  translatedName: string,
) => (saved && !shippedNames.has(saved.name) ? saved.name : translatedName);

export const ApplicationTopologyFilterLinkage = ({
  definitions,
}: {
  definitions: UnifiedFilterDefinition[];
}) => {
  const { t } = useTranslation();
  const systemSaved = definitions.find((item) => item.id === APPLICATION_TOPOLOGY_FILTER_ID);
  const depthSaved = definitions.find((item) => item.id === APPLICATION_TOPOLOGY_DEPTH_FILTER_ID);
  const systemName = linkageName(
    systemSaved,
    SHIPPED_SYSTEM_NAMES,
    t('dashboard.applicationTopologyFilterName'),
  );
  const depthName = linkageName(
    depthSaved,
    SHIPPED_DEPTH_NAMES,
    t('dashboard.applicationTopologyDepth'),
  );
  const dataSourceParams: ParamItem[] = [
    {
      name: APPLICATION_TOPOLOGY_FILTER_KEY,
      alias_name: systemName,
      type: 'string',
      filterType: 'filter',
      value: null,
    },
    {
      name: APPLICATION_TOPOLOGY_DEPTH_FILTER_KEY,
      alias_name: depthName,
      type: 'string',
      filterType: 'filter',
      value: null,
    },
  ];
  const displayDefinitions: UnifiedFilterDefinition[] = [
    {
      id: APPLICATION_TOPOLOGY_FILTER_ID,
      key: APPLICATION_TOPOLOGY_FILTER_KEY,
      name: systemName,
      type: 'string',
      enabled: true,
      order: systemSaved?.order ?? 0,
    },
    {
      id: APPLICATION_TOPOLOGY_DEPTH_FILTER_ID,
      key: APPLICATION_TOPOLOGY_DEPTH_FILTER_KEY,
      name: depthName,
      type: 'string',
      enabled: true,
      order: depthSaved?.order ?? 1,
    },
  ];

  return (
    <>
      <FilterBindingPanel
        definitions={displayDefinitions}
        dataSourceParams={dataSourceParams}
        filterBindings={{
          [APPLICATION_TOPOLOGY_FILTER_ID]: true,
          [APPLICATION_TOPOLOGY_DEPTH_FILTER_ID]: true,
        }}
      />
      <Form.Item
        name={['applicationTopology', 'depth']}
        hidden
        initialValue={APPLICATION_TOPOLOGY_DEFAULT_DEPTH}
      >
        <Input />
      </Form.Item>
    </>
  );
};
