import { Checkbox, Modal } from 'antd';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useTranslation } from '@/utils/i18n';

const NOTICE_KEY = 'opspilot.studio.retirement.2027-01.v1';

export default function StudioRetirementNotice({ userId }: { userId: string }) {
  const { t } = useTranslation();
  const storageKey = `${NOTICE_KEY}.${userId}`;
  const [open, setOpen] = useState(false);
  const [mute, setMute] = useState(false);

  useEffect(() => {
    try {
      setOpen(window.localStorage.getItem(storageKey) !== 'true');
    } catch {
      setOpen(true);
    }
  }, [storageKey]);

  const acknowledge = () => {
    if (mute) {
      try {
        window.localStorage.setItem(storageKey, 'true');
      } catch {
        // This visit can still be dismissed when browser storage is unavailable.
      }
    }
    setOpen(false);
  };

  return (
    <Modal
      open={open}
      centered
      title={t('studio.retirementNotice.title')}
      okText={t('studio.retirementNotice.acknowledge')}
      footer={(_, { OkBtn }) => (
        <div className="flex flex-col items-end gap-2">
          <Checkbox checked={mute} onChange={(event) => setMute(event.target.checked)}>
            {t('studio.retirementNotice.muteInBrowser')}
          </Checkbox>
          <OkBtn />
        </div>
      )}
      maskClosable={false}
      onOk={acknowledge}
      onCancel={() => setOpen(false)}
    >
      <p className="mb-2">{t('studio.retirementNotice.description')}</p>
      <Link href="/workflow" prefetch={false} className="text-[var(--color-primary)] hover:underline">
        {t('studio.retirementNotice.openWorkflow')}
      </Link>
    </Modal>
  );
}
