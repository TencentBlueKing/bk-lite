import { topLabelBars } from '../../shared/utils';
import type { BarItem } from '../../shared/widgets';

/**
 * 按 node_name 的 topk/bottomk 结果 → BarList。
 * 走共享 topLabelBars：会丢掉 fill_missing_points 补的 null（Number(null)===0）。
 */
export const topNodeBars = (raw: any, unit: string, color: string): BarItem[] =>
  topLabelBars(raw, unit, color, ['node_name']);
