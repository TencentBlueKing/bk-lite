'use client';

import React, { useMemo, useRef } from 'react';
import { Empty } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import usePermissions from '@/hooks/usePermissions';
import LogExtractorDrawer from '@/app/log/(pages)/integration/receive/logExtractorDrawer';
import {
  consumeExtractorCreateSample,
  isTypeScopedCollectType
} from '@/app/log/(pages)/integration/receive/logExtractorLogic';

const TypeExtractorPage = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { hasPermission } = usePermissions(
    '/log/integration/list/detail/configure'
  );
  const collectTypeName = searchParams.get('name') || '';
  const displayName =
    searchParams.get('display_name') || collectTypeName;
  const createRequested = useRef(searchParams.get('create') === '1');
  const initialSample = useMemo(
    () =>
      createRequested.current && collectTypeName
        ? consumeExtractorCreateSample({
            kind: 'type',
            id: collectTypeName
          })
        : null,
    [collectTypeName]
  );
  const canOperate = hasPermission(['Add']);

  if (!isTypeScopedCollectType(collectTypeName)) {
    return (
      <div className="p-4 bg-[var(--color-bg-1)]">
        <Empty description={t('log.extractor.unsupportedCollectType')} />
      </div>
    );
  }

  return (
    <LogExtractorDrawer
      collectType={{
        name: collectTypeName,
        displayName,
        canOperate
      }}
      open
      presentation="page"
      autoCreate={createRequested.current}
      initialSample={initialSample}
    />
  );
};

export default TypeExtractorPage;
