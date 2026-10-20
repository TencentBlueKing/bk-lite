import styles from './layered.module.scss';

/** 重点关注卡标题行：文案右侧一次浅灰单位。无单位时不占位。 */
export default function FocusShortcutTitle({
  label,
  unit
}: {
  label: string;
  unit?: string;
}) {
  return (
    <div className={styles.shortcutLabel}>
      <span className={styles.shortcutLabelText}>{label}</span>
      {unit ? <span className={styles.shortcutAxisUnit}>{unit}</span> : null}
    </div>
  );
}
