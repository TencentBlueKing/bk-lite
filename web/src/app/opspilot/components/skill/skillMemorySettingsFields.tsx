'use client';

import React from 'react';
import Link from 'next/link';
import { Form, InputNumber, Select, Tooltip } from 'antd';
import { PlusOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import type { WorkflowMemorySpaceOption } from '@/app/opspilot/api/memory';

interface SkillMemorySettingsFieldsProps {
  spaces: WorkflowMemorySpaceOption[];
  loading?: boolean;
}

const SkillMemorySettingsFields: React.FC<SkillMemorySettingsFieldsProps> = ({
  spaces,
  loading = false,
}) => {
  const { t } = useTranslation();
  const selectedSpaceId = Form.useWatch('memory_space');
  const personalSpaces = spaces.filter((space) => space.scope === 'personal');

  return (
    <Form.Item label={t('skill.memory.space')} className="!mb-3.5">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Form.Item name="memory_space" noStyle>
            <Select
              allowClear
              showSearch
              loading={loading}
              placeholder={t('skill.memory.spacePlaceholder')}
              optionFilterProp="label"
              className="min-w-0 flex-1"
              options={personalSpaces.map((space) => ({
                value: space.id,
                label: space.name,
              }))}
            />
          </Form.Item>
          <Link
            href="/opspilot/memory"
            target="_blank"
            className="inline-flex shrink-0 items-center gap-1 text-xs text-[var(--color-primary)] hover:opacity-80"
          >
            <PlusOutlined className="text-[10px]" />
            {t('chatflow.nodeConfig.addMemorySpace')}
          </Link>
        </div>

        {selectedSpaceId ? (
          <div className="flex items-center justify-between rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)]/60 px-3 py-2 text-xs">
            <div className="flex items-center gap-1.5 text-[var(--color-text-2)]">
              <span>{t('skill.memory.writeRounds')}</span>
              <Tooltip title={t('skill.memory.writeRoundsTip')}>
                <QuestionCircleOutlined className="text-[11px] text-[var(--color-text-4)] hover:text-[var(--color-text-3)] cursor-pointer" />
              </Tooltip>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[var(--color-text-3)]">{t('skill.memory.writeRoundsPrefix')}</span>
              <Form.Item name="memory_write_rounds" noStyle>
                <InputNumber min={1} max={50} size="small" className="w-16" />
              </Form.Item>
              <span className="text-[var(--color-text-3)]">{t('skill.memory.writeRoundsSuffix')}</span>
            </div>
          </div>
        ) : null}
      </div>
    </Form.Item>
  );
};

export default SkillMemorySettingsFields;

