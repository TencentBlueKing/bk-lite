import { useMemo } from 'react';
import { useTranslation } from '@/utils/i18n';
import { ApartmentOutlined, BarsOutlined } from '@ant-design/icons';
import { ObjectIconMap } from '@/app/monitor/types';

const useTableOptions = () => {
  return [
    { value: 'list', icon: <BarsOutlined /> },
    { value: 'view', icon: <ApartmentOutlined /> },
  ];
};

const useInterfaceLabelMap = (): ObjectIconMap => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      interface: t('monitor.views.interface'),
      ifOperStatus: t('monitor.views.ifOperStatus'),
      ifHighSpeed: t('monitor.views.ifHighSpeed'),
      ifInErrors: t('monitor.views.ifInErrors'),
      ifOutErrors: t('monitor.views.ifOutErrors'),
      ifInUcastPkts: t('monitor.views.ifInUcastPkts'),
      ifOutUcastPkts: t('monitor.views.ifOutUcastPkts'),
      ifInOctets: t('monitor.views.ifInOctets'),
      ifOutOctets: t('monitor.views.ifOutOctets'),
    }),
    [t]
  );
};

export { useTableOptions, useInterfaceLabelMap };
