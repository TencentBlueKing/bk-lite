'use client';

import React from 'react';
import { Form, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';

/** 放在知识库多选下方。没选知识库时禁用，不改已保存的开关值。 */
const SkillWikiMaterialWriteField: React.FC = () => {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const wikiKbIds = Form.useWatch('wiki_knowledge_bases', form);
  const hasWikiKb = Array.isArray(wikiKbIds) && wikiKbIds.length > 0;

  return (
    <div className="flex items-center gap-2">
      <Form.Item name="allow_wiki_material_write" valuePropName="checked" noStyle>
        <Switch size="small" disabled={!hasWikiKb} />
      </Form.Item>
      <span
        className={`select-none text-xs ${
          hasWikiKb
            ? 'cursor-pointer text-[var(--color-text-2)] hover:text-[var(--color-text-1)]'
            : 'cursor-not-allowed text-[var(--color-text-4)]'
        }`}
        onClick={() => {
          if (!hasWikiKb) {
            return;
          }
          form.setFieldValue(
            'allow_wiki_material_write',
            !form.getFieldValue('allow_wiki_material_write'),
          );
        }}
      >
        {t('skill.form.allowWikiMaterialWrite')}
      </span>
    </div>
  );
};

export default SkillWikiMaterialWriteField;
