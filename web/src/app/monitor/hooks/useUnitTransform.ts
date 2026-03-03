import { useCommon } from '@/app/monitor/context/common';
import { MetricItem } from '@/app/monitor/types';
import { APPOINT_METRIC_IDS } from '@/app/monitor/constants';
import { isStringArray } from '@/app/monitor/utils/common';
import { ListItem } from '@/app/monitor/types';

export const useUnitTransform = () => {
  const commonContext = useCommon();
  const unitList = commonContext?.unitList || [];

  const findUnitNameById = (value: unknown, displayUnit?: string): string => {
    const vacantUnits = ['short', 'none', 'counts'];
    if (
      !value ||
      vacantUnits.includes(value as string) ||
      isStringArray(value as string)
    ) {
      return '';
    }
    let unit: any = unitList.find((item) => item.unit_id === value);
    if (displayUnit) {
      unit = {
        display_unit: displayUnit,
      };
    }
    const isVacantUnit = vacantUnits.includes(unit?.display_unit);
    return isVacantUnit ? '' : unit?.display_unit || value?.toString() || '';
  };

  const getEnumValueUnit = (
    metric: MetricItem,
    id: number | string,
    displayUnit?: string
  ) => {
    const { unit: input = '', name } = metric || {};
    if (!id && id !== 0) return '--';
    if (isStringArray(input)) {
      return (
        JSON.parse(input).find((item: ListItem) => item.id === +id)?.name || id
      );
    }
    const unit = findUnitNameById(input, displayUnit);
    return isNaN(+id) || APPOINT_METRIC_IDS.includes(name)
      ? `${id} ${unit}`
      : `${(+id).toFixed(2)} ${unit}`;
  };

  return { findUnitNameById, getEnumValueUnit };
};
