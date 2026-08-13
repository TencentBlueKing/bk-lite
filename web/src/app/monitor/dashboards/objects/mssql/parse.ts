import { topLabelBars } from '../../shared/utils';
import type { BarItem } from '../../shared/widgets';

/**
 * 按 database_name 的 topk 结果 → BarList。
 * 走共享 topLabelBars：会丢掉 fill_missing_points 补的 null（Number(null)===0），
 * 避免「取最后一个点」拿到占位 0 导致整列显示 0ms。
 */
export const topDbBars = (raw: any, unit: string, color: string): BarItem[] =>
  topLabelBars(raw, unit, color, ['database_name']);
