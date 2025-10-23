import { useTranslation } from '@/utils/i18n';
import { useMemo } from 'react';

const useControllerMenuItem = () => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        key: 'upload',
        role: 'AddPacket',
        title: t('node-manager.packetManage.uploadPackage'),
        config: {
          title: t('node-manager.packetManage.uploadPackage'),
          type: 'upload',
        },
      },
    ],
    [t]
  );
};

export { useControllerMenuItem };
