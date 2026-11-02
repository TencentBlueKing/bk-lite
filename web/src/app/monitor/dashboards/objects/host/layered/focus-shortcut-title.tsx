import type { ReactNode } from 'react';
import { formatFocusUnitText } from './focus-axis';
import styles from './layered.module.scss';

/** 重点关注卡标题行：文案右侧一次浅灰 (单位)。无单位不加空括号。hint 紧挨标题。 */
export default function FocusShortcutTitle({
  label,
  unit,
  hint
}: {
  label: string;
  unit?: string;
  hint?: ReactNode;
}) {
  const unitText = formatFocusUnitText(unit);
  return (
    <div className={styles.shortcutLabel}>
      <span className={styles.shortcutLabelText}>{label}</span>
      {hint ? <span className="inline-flex shrink-0 items-center self-center">{hint}</span> : null}
      {unitText ? <span className={styles.shortcutAxisUnit}>{unitText}</span> : null}
    </div>
  );
}
