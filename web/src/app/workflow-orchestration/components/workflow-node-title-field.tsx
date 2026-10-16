'use client';

import { Form, Input } from 'antd';

import { useTranslation } from '@/utils/i18n';

import { ReferenceDropGuard } from './reference-drop-guard';

/** 节点名称：设计态展示标签，仅普通文本；不支持拖入上游字段与 `$` 提示。 */
export function WorkflowNodeTitleField({
  value,
  disabled = false,
  onChange,
}: {
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <Form.Item className="mb-0" label={t('workflowOrchestration.editor.nodeName', '节点名称')} required>
      <ReferenceDropGuard
        reason={t(
          'workflowOrchestration.editor.nodeNameDropRejected',
          '节点名称只用于画布展示，不支持拖入上游字段',
        )}
      >
        <Input
          disabled={disabled}
          value={value}
          placeholder={t('workflowOrchestration.editor.enterNodeName', '请输入节点名称')}
          onChange={(event) => onChange(event.target.value)}
        />
      </ReferenceDropGuard>
    </Form.Item>
  );
}
