'use client';

import { PatchSourcesSettings } from '../_components/settings-content';
import styles from '../page.module.scss';

export default function PatchSourcesSettingsPage() {
  return (
    <div className={styles.settingsContainer}>
      <PatchSourcesSettings />
    </div>
  );
}
