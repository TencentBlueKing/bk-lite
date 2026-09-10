'use client';

import React, { useEffect, useRef, useState } from 'react';
import CompactEmptyState from '@/components/compact-empty-state';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import usePermissions from '@/hooks/usePermissions';
import LogExtractorDrawer from '@/app/log/(pages)/integration/receive/logExtractorDrawer';
import {
  consumeExtractorCreateHandoff,
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
  const createContextConsumed = useRef(false);
  const [initialSample, setInitialSample] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [initialSourceField, setInitialSourceField] = useState<string | null>(
    null
  );
  const [createContextReady, setCreateContextReady] = useState(
    !createRequested.current
  );
  const canOperate = hasPermission(['Add']);

  useEffect(() => {
    if (!createRequested.current || createContextConsumed.current) return;
    createContextConsumed.current = true;
    const handoff = consumeExtractorCreateHandoff(searchParams.get('handoff'));
    setInitialSample(
      handoff?.event ||
        (collectTypeName
          ? consumeExtractorCreateSample({
              kind: 'type',
              id: collectTypeName
            })
          : null)
    );
    setInitialSourceField(
      handoff?.source_field || searchParams.get('source_field')
    );
    setCreateContextReady(true);
  }, [collectTypeName, searchParams]);

  if (!isTypeScopedCollectType(collectTypeName)) {
    return (
      <div className="p-4 bg-[var(--color-bg-1)]">
        <CompactEmptyState description={t('log.extractor.unsupportedCollectType')} />
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
      autoCreate={createRequested.current && createContextReady}
      initialSample={initialSample}
      initialSourceField={initialSourceField}
    />
  );
};

export default TypeExtractorPage;
