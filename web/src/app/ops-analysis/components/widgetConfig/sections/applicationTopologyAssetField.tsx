'use client';

import React from 'react';
import { Form, Select } from 'antd';
import { FilterBindingPanel } from '@/app/ops-analysis/components/unifiedFilter';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import { useTranslation } from '@/utils/i18n';
import {
  APPLICATION_TOPOLOGY_DEFAULT_DEPTH,
  APPLICATION_TOPOLOGY_MAX_DEPTH,
} from '@/app/ops-analysis/types/sceneWidget';
import {
  APPLICATION_TOPOLOGY_FILTER_ID,
  APPLICATION_TOPOLOGY_FILTER_KEY,
  APPLICATION_TOPOLOGY_FILTER_NAME,
} from '@/app/ops-analysis/utils/applicationTopologyCanvasFilter';

const DEPTH_OPTIONS = Array.from(
  { length: APPLICATION_TOPOLOGY_MAX_DEPTH },
  (_, index) => {
    const value = index + 1;
    return { value, label: String(value) };
  },
);

export const ApplicationTopologyFilterLinkage = ({
  definitions,
}: {
  definitions: UnifiedFilterDefinition[];
}) => {
  const { t } = useTranslation();
  const saved = definitions.find((item) => item.id === APPLICATION_TOPOLOGY_FILTER_ID);
  const displayName = saved && saved.name !== APPLICATION_TOPOLOGY_FILTER_NAME
    ? saved.name
    : t('dashboard.applicationTopologyFilterName');
  const dataSourceParams: ParamItem[] = [
    {
      name: APPLICATION_TOPOLOGY_FILTER_KEY,
      alias_name: displayName,
      type: 'string',
      filterType: 'filter',
      value: null,
    },
  ];
  const displayDefinitions: UnifiedFilterDefinition[] = [
    {
      id: APPLICATION_TOPOLOGY_FILTER_ID,
      key: APPLICATION_TOPOLOGY_FILTER_KEY,
      name: displayName,
      type: 'string',
      enabled: true,
      order: saved?.order ?? 0,
    },
  ];

  return (
    <FilterBindingPanel
      definitions={displayDefinitions}
      dataSourceParams={dataSourceParams}
      filterBindings={{ [APPLICATION_TOPOLOGY_FILTER_ID]: true }}
    />
  );
};

export const ApplicationTopologyDepthField = () => {
  const { t } = useTranslation();
  return (
    <Form.Item
      label={t('dashboard.applicationTopologyDepth')}
      name={['applicationTopology', 'depth']}
      initialValue={APPLICATION_TOPOLOGY_DEFAULT_DEPTH}
      extra={t('dashboard.applicationTopologyDepthHelp')}
    >
      <Select options={DEPTH_OPTIONS} />
    </Form.Item>
  );
};
