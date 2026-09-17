import { GuideItem } from '../../shared/types';

/** 网络设备温度 KPI / 趋势图共用悬浮指引：解释正常读数与 65535 哨兵。 */
export const DEVICE_TEMPERATURE_KPI_GUIDE: GuideItem[] = [
  {
    label: '最高温度',
    detail: '设备各温度传感器读数中的最高值（℃）。异常升高可能是风扇故障、风道堵塞或环境过热。'
  },
  {
    label: '无传感器',
    detail:
      '部分厂商（如华三 H3C）对没有温度传感器的硬件实体，会通过 SNMP 上报固定值 65535（16 位整数上限）表示「不支持/不可用」，这不是真实温度。仪表盘识别后显示「无传感器」。若显示「--」，表示当前时间窗口内没有采到温度数据。'
  }
];

export const DEVICE_TEMPERATURE_CHART_GUIDE: GuideItem[] = [
  {
    label: '温度趋势',
    detail: '最高有效传感器温度随时间变化；持续上升需关注散热。'
  },
  {
    label: '无传感器',
    detail:
      '若设备仅上报 65535（厂商表示该实体无温度传感器/不支持），趋势图为空，KPI 显示「无传感器」，并非采集失败。有有效读数时不会把 65535 计入最高温度。'
  }
];
