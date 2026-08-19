'use client';

import { ScanSettings } from '../_components/settings-content';
import styles from '../page.module.scss';

export default function ScanSettingsPage() {
  return (
    <div className={`${styles.settingsContainer} ${styles.scanSettingsContent}`}>
      <ScanSettings />
    </div>
  );
}
