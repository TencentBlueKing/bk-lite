import { useTranslation } from '@/utils/i18n';
import { useMemo } from 'react';
import { StateMap } from '@/app/alarm/types/alarms';

export const baseStates = ['pending', 'processing', 'unassigned'] as const;
export const allStates = [...baseStates, 'closed', 'recovered', 'auto_close'] as const;
export const incidentStates = ['pending', 'processing', 'closed'] as const;

const useStateMap = (): StateMap => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      new: t('alarms.new'),
      closed: t('alarms.closed'),
      pending: t('alarms.pending'),
      processing: t('alarms.processing'),
      unassigned: t('alarms.unassigned'),
      auto_close: t('alarms.auto_close'),
      resolved: t('alarms.resolved'),
      shield: t('alarms.shield'),
      received: t('alarms.received'),
      auto_recovery: t('alarms.auto_recovery'),
    }),
    [t]
  );
};

const useNotifiedStateMap = () => {
  const { t } = useTranslation();
  return useMemo(() => {
    return {
      not_notified: t('alarmCommon.notNotified'),
      success: t('alarmCommon.success'),
      fail: t('alarmCommon.fail'),
      partial_success: t('alarmCommon.partialSuccess'),
    };
  }, [t]);
};

export {
  useStateMap,
  useNotifiedStateMap,
};
