import { useTranslation } from '@/utils/i18n';
import { useMemo } from 'react';

const useMenuItem = () => {
  const { t } = useTranslation();
  return useMemo(() => [
    {
      key: 'edit',
      role: 'Edit',
      title: 'edit',
      config: {
        title: 'editCollector', type: 'edit'
      }
    },
    {
      key: 'upload',
      role: 'AddPacket',
      title: 'uploadPackage',
      config: {
        title: 'uploadPackage', type: 'upload'
      }
    },
    {
      key: 'delete',
      role: 'Delete',
      title: 'delete',
      config: {
        title: 'deleteCollector', type: 'delete'
      }
    }
  ],[t])
};

export {
  useMenuItem
}