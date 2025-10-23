import { useMemo } from 'react';
import { useTranslation } from '@/utils/i18n';

const useCollectorMenuItem = () => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        key: 'edit',
        role: 'Edit',
        title: t('common.edit'),
        config: {
          title: t('node-manager.collector.editCollector'),
          type: 'edit',
        },
      },
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

export { useCollectorMenuItem };
