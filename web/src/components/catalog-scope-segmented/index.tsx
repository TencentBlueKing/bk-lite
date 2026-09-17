'use client';

import { ApartmentOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';

export interface CatalogScopeSegmentedProps {
  unassignedOnly: boolean;
  onChange: (unassignedOnly: boolean) => void;
  count?: number;
  resourceName?: string;
  className?: string;
}

const joinClassNames = (...values: Array<string | false | undefined>) =>
  values.filter(Boolean).join(' ');

const CatalogScopeSegmented = ({
  unassignedOnly,
  onChange,
  count,
  resourceName,
  className = '',
}: CatalogScopeSegmentedProps) => {
  const { t } = useTranslation();
  const { isSuperUser, loading } = useUserInfoContext();

  if (loading || !isSuperUser) {
    return null;
  }

  const resource = resourceName || t('common.instance', '实例');
  const hasCount = typeof count === 'number' && count > 0;

  return (
    <Button
      type={unassignedOnly ? 'primary' : 'default'}
      icon={<ApartmentOutlined aria-hidden="true" />}
      aria-pressed={unassignedOnly}
      aria-label={
        unassignedOnly
          ? t('common.unassignedViewingNotice', '正在查看未归属{resource}', { resource })
          : t('common.unassignedDetectedNotice', '有未归属{resource}，普通成员不可见', { resource })
      }
      className={joinClassNames('shrink-0', className)}
      onClick={() => onChange(!unassignedOnly)}
    >
      {t('common.unassigned', '未归属')}
      {hasCount ? (
        <span
          className={joinClassNames(
            'ml-1 tabular-nums',
            !unassignedOnly && 'text-[var(--color-text-3)]',
          )}
        >
          {count}
        </span>
      ) : null}
    </Button>
  );
};

export default CatalogScopeSegmented;
export { CatalogScopeSegmented };
export type { CatalogScopeSegmentedProps };
