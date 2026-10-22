'use client';

import { QuestionCircleOutlined } from '@ant-design/icons';
import { Tooltip } from 'antd';
import { formatFocusUnitText } from './focus-axis';
import styles from './layered.module.scss';

/** 重点关注卡标题行：文案右侧一次浅灰 (单位)。无单位不加空括号。有 hint 才在标题旁出 ?。 */
export default function FocusShortcutTitle({
  label,
  unit,
  hint
}: {
  label: string;
  unit?: string;
  /** 标题旁悬浮说明。主机不传则不渲染 ?。 */
  hint?: string;
}) {
  const unitText = formatFocusUnitText(unit);
  return (
    <div className={styles.shortcutLabel}>
      <span className={styles.shortcutLabelText}>{label}</span>
      {hint ? (
        <Tooltip title={hint} styles={{ body: { maxWidth: 360 } }}>
          <QuestionCircleOutlined
            className="cursor-help self-center text-[12px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]"
            aria-label={hint}
          />
        </Tooltip>
      ) : null}
      {unitText ? <span className={styles.shortcutAxisUnit}>{unitText}</span> : null}
    </div>
  );
}
