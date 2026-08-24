'use client';

import { useParams } from 'next/navigation';
import { Empty } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import { isValidViewType } from '../viewTypes';
import ViewsWorkspaceShell from '../components/ViewsWorkspaceShell';

export default function CmdbViewPage() {
  const { t } = useTranslation();
  const params = useParams();
  const raw = params.viewType;
  const viewType = Array.isArray(raw) ? raw[0] : raw;
  if (!viewType || !isValidViewType(viewType)) {
    return <CompactEmptyState description={t('ViewsHub.unknownView')} />;
  }
  return <ViewsWorkspaceShell key={viewType} viewType={viewType} />;
}
