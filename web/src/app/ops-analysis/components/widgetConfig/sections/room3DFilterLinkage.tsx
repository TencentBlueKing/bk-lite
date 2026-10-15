'use client';

import React from 'react';
import { FilterBindingPanel } from '@/app/ops-analysis/components/unifiedFilter';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import { useTranslation } from '@/utils/i18n';
import {
  ROOM3D_FILTER_ID,
  ROOM3D_FILTER_KEY,
  ROOM3D_FILTER_NAME,
} from '@/app/ops-analysis/utils/room3DScreenFilter';

interface Room3DFilterLinkageProps {
  definitions: UnifiedFilterDefinition[];
}

const Room3DFilterLinkage: React.FC<Room3DFilterLinkageProps> = ({
  definitions,
}) => {
  const { t } = useTranslation();
  const saved = definitions.find((item) => item.id === ROOM3D_FILTER_ID);
  const displayName = saved && saved.name !== ROOM3D_FILTER_NAME
    ? saved.name
    : t('dashboard.room3DFilterName');
  const dataSourceParams: ParamItem[] = [
    {
      name: ROOM3D_FILTER_KEY,
      alias_name: displayName,
      type: 'string',
      filterType: 'filter',
      value: null,
    },
  ];
  const displayDefinitions: UnifiedFilterDefinition[] = [
    {
      id: ROOM3D_FILTER_ID,
      key: ROOM3D_FILTER_KEY,
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
      filterBindings={{ [ROOM3D_FILTER_ID]: true }}
    />
  );
};

export default Room3DFilterLinkage;
