'use client';

import React from 'react';
import Link from 'next/link';
import { Form, InputNumber, Select } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
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
    <>
      <Form.Item
        label={t('skill.memory.space')}
        name="memory_space"
        extra={
          <Link
            href="/opspilot/memory"
            target="_blank"
            className="inline-flex items-center gap-1 text-xs text-[var(--color-primary)]"
          >
            <PlusOutlined className="text-[10px]" />
            {t('chatflow.nodeConfig.addMemorySpace')}
          </Link>
        }
      >
        <Select
          allowClear
          showSearch
          loading={loading}
          placeholder={t('skill.memory.spacePlaceholder')}
          optionFilterProp="label"
          options={personalSpaces.map((space) => ({
            value: space.id,
            label: space.name,
          }))}
        />
      </Form.Item>
      {selectedSpaceId ? (
        <Form.Item
          label={t('skill.memory.writeRounds')}
          tooltip={t('skill.memory.writeRoundsTip')}
          className="!mb-3.5"
        >
          <div className="flex h-8 items-center gap-2">
            <Form.Item name="memory_write_rounds" noStyle>
              <InputNumber min={1} max={50} size="small" className="w-16" />
            </Form.Item>
            <span className="text-xs text-[var(--color-text-3)]">轮</span>
          </div>
        </Form.Item>
      ) : null}
    </>
  );
};

export default SkillMemorySettingsFields;
