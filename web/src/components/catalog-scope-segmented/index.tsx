'use client';

import { Segmented } from 'antd';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';

type CatalogScope = 'current' | 'unassigned';

export interface CatalogScopeSegmentedProps {
  unassignedOnly: boolean;
  onChange: (unassignedOnly: boolean) => void;
  className?: string;
}

const CatalogScopeSegmented = ({
  unassignedOnly,
  onChange,
  className,
}: CatalogScopeSegmentedProps) => {
  const { t } = useTranslation();
  const { isSuperUser, loading } = useUserInfoContext();

  if (loading || !isSuperUser) {
    return null;
  }

  return (
    <Segmented<CatalogScope>
      aria-label={t('common.catalogScope')}
      className={className}
      value={unassignedOnly ? 'unassigned' : 'current'}
      options={[
        { value: 'current', label: t('common.currentOrganization') },
        { value: 'unassigned', label: t('common.unassigned') },
      ]}
      onChange={(value) => onChange(value === 'unassigned')}
    />
  );
};

export default CatalogScopeSegmented;
