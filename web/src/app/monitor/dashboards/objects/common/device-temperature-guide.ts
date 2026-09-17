import { GuideItem } from '../../shared/types';

/** 通用温度 KPI 指引（不含品牌哨兵说明；哨兵文案由 unavailable-contract 注入）。 */
export const GENERIC_DEVICE_TEMPERATURE_KPI_GUIDE: GuideItem[] = [
  {
    label: '最高温度',
    detail: '设备各温度传感器读数中的最高值（℃）。异常升高可能是风扇故障、风道堵塞或环境过热。'
  }
];

export const GENERIC_DEVICE_TEMPERATURE_CHART_GUIDE: GuideItem[] = [
  {
    label: '温度趋势',
    detail: '最高有效传感器温度随时间变化；持续上升需关注散热。'
  }
];

/** @deprecated 使用 GENERIC_*；保留别名避免外部误引用。 */
export const DEVICE_TEMPERATURE_KPI_GUIDE = GENERIC_DEVICE_TEMPERATURE_KPI_GUIDE;
export const DEVICE_TEMPERATURE_CHART_GUIDE = GENERIC_DEVICE_TEMPERATURE_CHART_GUIDE;
