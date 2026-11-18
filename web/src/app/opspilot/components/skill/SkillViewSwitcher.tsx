'use client';

import { Segmented } from 'antd';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';

type SkillView = 'agents' | 'templates';

const VIEW_PATHS = {
  agents: '/opspilot/skill',
  templates: '/opspilot/skill/templates',
};

export default function SkillViewSwitcher({ value }: { value: SkillView }) {
  const router = useRouter();
  const { t } = useTranslation();

  return (
    <div className="mb-4 flex flex-col">
      <Segmented<SkillView>
        className="self-start"
        value={value}
        onChange={(view) => router.push(VIEW_PATHS[view])}
        options={[
          { label: t('skill.pageTitle'), value: 'agents' },
          { label: t('skill.templatesTitle'), value: 'templates' },
        ]}
      />
    </div>
  );
}
