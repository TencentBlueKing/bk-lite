import { useMemo } from 'react';
import { ListItem } from '@/types';
import { useTranslation } from '@/utils/i18n';

const useAlertDetailTabs = () => {
  const { t } = useTranslation();
  return [
    {
      label: t('common.detail'),
      key: 'information',
    },
    {
      label: t('monitor.events.event'),
      key: 'event',
    },
  ];
};

const useAlarmTabs = () => {
  const { t } = useTranslation();
  return [
    {
      label: t('monitor.events.activeAlarms'),
      key: 'activeAlarms',
    },
    {
      label: t('monitor.events.historicalAlarms'),
      key: 'historicalAlarms',
    },
  ];
};

const useStateList = () => {
  const { t } = useTranslation();
  return [
    {
      label: t('monitor.events.new'),
      value: 'new',
    },
    {
      label: t('monitor.events.recovery'),
      value: 'recovered',
    },
    {
      label: t('monitor.events.closed'),
      value: 'closed',
    },
  ];
};

const useScheduleList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { label: t('monitor.events.minutes'), value: 'min' },
      { label: t('monitor.events.hours'), value: 'hour' },
      { label: t('monitor.events.days'), value: 'day' },
    ],
    [t]
  );
};

const useMethodList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { label: 'SUM', value: 'sum', title: t('monitor.events.sumTitle') },
      {
        label: 'SUM_OVER_TIME',
        value: 'sum_over_time',
        title: t('monitor.events.sumOverTimeTitle'),
      },
      { label: 'MAX', value: 'max', title: t('monitor.events.maxTitle') },
      {
        label: 'MAX_OVER_TIME',
        value: 'max_over_time',
        title: t('monitor.events.maxOverTimeTitle'),
      },
      { label: 'MIN', value: 'min', title: t('monitor.events.minTitle') },
      {
        label: 'MIN_OVER_TIME',
        value: 'min_over_time',
        title: t('monitor.events.minOverTimeTitle'),
      },
      { label: 'AVG', value: 'avg', title: t('monitor.events.avgTitle') },
      {
        label: 'AVG_OVER_TIME',
        value: 'avg_over_time',
        title: t('monitor.events.avgOverTimeTitle'),
      },
      { label: 'COUNT', value: 'count', title: t('monitor.events.countTitle') },
      {
        label: 'LAST_OVER_TIME',
        value: 'last_over_time',
        title: t('monitor.events.lastOverTimeTitle'),
      },
    ],
    [t]
  );
};

export {
  useAlertDetailTabs,
  useAlarmTabs,
  useStateList,
  useScheduleList,
  useMethodList,
};
