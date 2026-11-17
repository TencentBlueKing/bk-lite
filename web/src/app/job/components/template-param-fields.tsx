'use client';

import React from 'react';
import { Form, Input, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import Password from '@/components/password';
import ParamTipText from '@/app/job/components/param-tip-text';
import type { ScriptParam } from '@/app/job/types';

export function TemplateParamFields({
  params,
  onEncryptedReset,
}: {
  params: ScriptParam[];
  onEncryptedReset: (name: string) => void;
}) {
  const { t } = useTranslation();
  if (params.length === 0) return null;

  return (
    <>
      <div className="text-sm font-medium mb-2 text-[var(--color-text-2)]">
        {t('job.execParams')}
      </div>
      {params.map((param) => {
        const isEnum = param.type === 'enum' && (param.options?.length || 0) > 0;
        return (
          <Form.Item
            key={param.name}
            label={param.name}
            name={`param_${param.name}`}
            initialValue={param.default || undefined}
            rules={[
              {
                required: !!param.is_required,
                message: t('job.paramValueRequired', undefined, { name: param.name }),
              },
            ]}
            tooltip={
              param.description
                ? {
                  title: <ParamTipText text={param.description} />,
                  mouseLeaveDelay: 0.3,
                }
                : undefined
            }
          >
            {isEnum ? (
              <Select
                allowClear={!param.is_required}
                placeholder={param.name}
                options={(param.options || []).map((opt) => ({
                  label: opt,
                  value: opt,
                }))}
              />
            ) : param.is_encrypted ? (
              <Password
                placeholder={param.name}
                clickToEdit={!!param.default}
                onReset={() => onEncryptedReset(param.name)}
              />
            ) : (
              <Input placeholder={param.name} />
            )}
          </Form.Item>
        );
      })}
    </>
  );
}
