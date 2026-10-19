'use client';

import React, { useEffect, useRef } from 'react';
import { Form } from 'antd';

import InteractionLinkSection from '@/app/ops-analysis/components/widgetConfig/sections/interactionLinkSection';
import { useFilterTemplateVariables } from '@/app/ops-analysis/context/filterTemplate';
import type { ScreenTextItem } from '@/app/ops-analysis/types/screen';
import { useTranslation } from '@/utils/i18n';
import { withScreenTextInteraction } from '../utils/screenTextInteraction';

const emptyInteraction = {
  kind: 'none' as const,
  name: '',
  url: '',
  openMode: 'sameTab' as const,
};

const ScreenTextLinkFields: React.FC<{
  item: ScreenTextItem;
  onChange: (item: ScreenTextItem) => void;
}> = ({ item, onChange }) => {
  const { t } = useTranslation();
  const definitions = useFilterTemplateVariables();
  const [form] = Form.useForm();
  const writingRef = useRef(false);
  const seenIdRef = useRef(item.id);
  const stored = item.interaction?.kind === 'title' ? item.interaction : undefined;
  const storedKey = stored ? JSON.stringify(stored) : '';
  const publish = (draft = form.getFieldValue('interaction')) => {
    const next = withScreenTextInteraction(item, draft);
    if (next === item) return;
    writingRef.current = true;
    onChange(next);
  };

  useEffect(() => {
    const idChanged = seenIdRef.current !== item.id;
    seenIdRef.current = item.id;
    const fromWrite = writingRef.current;
    writingRef.current = false;
    if (fromWrite && !idChanged) return;
    form.setFieldsValue({
      interaction: stored ?? emptyInteraction,
    });
  }, [form, item.id, stored, storedKey]);

  return (
    <Form
      form={form}
      component="div"
      layout="vertical"
      size="small"
      requiredMark={false}
      className="[&_.ant-form-item]:mb-3 [&_.ant-form-item-label>label]:text-xs"
      initialValues={{ interaction: stored ?? emptyInteraction }}
      onValuesChange={(_, all) => publish(all.interaction)}
    >
      <InteractionLinkSection
        t={t}
        definitions={definitions}
        rawData={null}
        besideText
        clearOnNone
        onDraftChange={() => publish()}
      />
    </Form>
  );
};

export default ScreenTextLinkFields;
