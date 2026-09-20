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
      {
        label: t('monitor.events.algorithmSumOverTime', '求和'),
        value: 'sum_over_time',
        title: t('monitor.events.sumOverTimeTitle'),
      },
      {
        label: t('monitor.events.algorithmMaxOverTime', '最大'),
        value: 'max_over_time',
        title: t('monitor.events.maxOverTimeTitle'),
      },
      {
        label: t('monitor.events.algorithmMinOverTime', '最小'),
        value: 'min_over_time',
        title: t('monitor.events.minOverTimeTitle'),
      },
      {
        label: t('monitor.events.algorithmAvgOverTime', '平均'),
        value: 'avg_over_time',
        title: t('monitor.events.avgOverTimeTitle'),
      },
      {
        label: t('monitor.events.algorithmCountOverTime', '点数'),
        value: 'count_over_time',
        title: t('monitor.events.countOverTimeTitle'),
      },
      {
        label: t('monitor.events.algorithmLastOverTime', '末值'),
        value: 'last_over_time',
        title: t('monitor.events.lastOverTimeTitle'),
      },
      {
        label: t('monitor.events.algorithmP90OverTime', 'P90'),
        value: 'p90_over_time',
        title: t('monitor.events.p90OverTimeTitle'),
      },
      {
        label: t('monitor.events.algorithmP95OverTime', 'P95'),
        value: 'p95_over_time',
        title: t('monitor.events.p95OverTimeTitle'),
      },
      {
        label: t('monitor.events.algorithmP99OverTime', 'P99'),
        value: 'p99_over_time',
        title: t('monitor.events.p99OverTimeTitle'),
      },
      {
        label: t('monitor.events.algorithmStddevOverTime', '标准差'),
        value: 'stddev_over_time',
        title: t('monitor.events.stddevOverTimeTitle'),
      },
      {
        label: t('monitor.events.algorithmCountIfOverTime', '条件计数'),
        value: 'count_if_over_time',
        title: t('monitor.events.countIfOverTimeTitle'),
      },
      {
        label: t('monitor.events.algorithmRate', '速率'),
        value: 'rate',
        title: t('monitor.events.rateTitle'),
      },
      {
        label: t('monitor.events.algorithmChanges', '变化次数'),
        value: 'changes',
        title: t('monitor.events.changesTitle'),
      },
      {
        label: t('monitor.events.algorithmDeriv', '斜率'),
        value: 'deriv',
        title: t('monitor.events.derivTitle'),
      },
    ],
    [t]
  );
};

const useGroupMethodList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { label: t('monitor.events.avg'), value: 'avg', title: t('monitor.events.avgTitle') },
      { label: t('monitor.events.max'), value: 'max', title: t('monitor.events.maxTitle') },
      { label: t('monitor.events.min'), value: 'min', title: t('monitor.events.minTitle') },
      { label: t('monitor.events.sum'), value: 'sum', title: t('monitor.events.sumTitle') },
      { label: t('monitor.events.count', '计数'), value: 'count', title: t('monitor.events.countTitle') },
    ],
    [t]
  );
};

const useEventActionMap = () => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      triggered: t('monitor.events.eventTriggered'),
      escalated: t('monitor.events.eventEscalated'),
      claimed: t('monitor.events.eventClaimed'),
      assigned: t('monitor.events.eventAssigned'),
      reassigned: t('monitor.events.eventReassigned'),
      recovered: t('monitor.events.eventRecovered'),
      closed: t('monitor.events.eventClosed'),
    }),
    [t]
  );
};

export {
  useAlertDetailTabs,
  useAlarmTabs,
  useStateList,
  useScheduleList,
  useMethodList,
  useGroupMethodList,
  useEventActionMap,
};
