import React, { useMemo } from 'react';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import type { MenuProps } from 'antd';

const useAssetMenuItems = (): MenuProps['items'] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        label: (
          <PermissionWrapper
            className="customMenuItem"
            requiredPermissions={['Edit']}
          >
            {t('common.batchEdit')}
          </PermissionWrapper>
        ),
        key: 'batchEdit',
      },
    ],
    [t]
  );
};
export { useAssetMenuItems };
