import { useTranslation } from '@/utils/i18n';
import { useMemo } from 'react';
import PermissionWrapper from '@/components/permission';
import type { MenuProps } from 'antd';

const useConfigBtachItems = (): MenuProps['items'] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        label: (
          <PermissionWrapper
            className="customMenuItem"
            requiredPermissions={['Delete']}
          >
            {t('common.delete')}
          </PermissionWrapper>
        ),
        key: 'delete',
      },
    ],
    [t]
  );
};

export { useConfigBtachItems };
