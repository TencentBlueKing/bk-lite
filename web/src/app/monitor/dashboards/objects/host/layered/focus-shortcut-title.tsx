import { formatFocusUnitText } from './focus-axis';
import styles from './layered.module.scss';

/** 重点关注卡标题行：文案右侧一次浅灰 (单位)。无单位不加空括号。 */
export default function FocusShortcutTitle({
  label,
  unit
}: {
  label: string;
  unit?: string;
}) {
  const unitText = formatFocusUnitText(unit);
  return (
    <div className={styles.shortcutLabel}>
      <span className={styles.shortcutLabelText}>{label}</span>
      {unitText ? <span className={styles.shortcutAxisUnit}>{unitText}</span> : null}
    </div>
  );
}
