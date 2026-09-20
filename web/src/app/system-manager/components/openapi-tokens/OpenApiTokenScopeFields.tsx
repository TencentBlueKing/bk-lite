'use client';

import React, { useState } from 'react';
import { Checkbox, Form, Radio, Tabs } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type {
  OpenApiTokenScopeMode,
  OpenApiTokenServiceCatalog,
} from './types';

interface OpenApiTokenScopeFieldsProps {
  catalog: OpenApiTokenServiceCatalog[];
}

interface EndpointPickerProps {
  catalog: OpenApiTokenServiceCatalog[];
  value?: string[];
  onChange?: (next: string[]) => void;
}

const EndpointPicker: React.FC<EndpointPickerProps> = ({
  catalog,
  value = [],
  onChange,
}) => {
  const { t } = useTranslation();
  const [activeService, setActiveService] = useState(catalog[0]?.name);
  const activeKey = catalog.some((item) => item.name === activeService)
    ? activeService
    : catalog[0]?.name;
  const service = catalog.find((item) => item.name === activeKey);
  const selected = new Set(value);

  const toggle = (key: string, checked: boolean) => {
    const next = new Set(value);
    if (checked) {
      next.add(key);
    } else {
      next.delete(key);
    }
    onChange?.(Array.from(next));
  };

  const toggleService = (item: OpenApiTokenServiceCatalog, checked: boolean) => {
    const next = new Set(value);
    item.endpoints.forEach((endpoint) => {
      if (checked) {
        next.add(endpoint.key);
      } else {
        next.delete(endpoint.key);
      }
    });
    onChange?.(Array.from(next));
  };

  const selectedCount = (item: OpenApiTokenServiceCatalog) => (
    item.endpoints.filter((endpoint) => selected.has(endpoint.key)).length
  );

  return (
    <div className="overflow-hidden rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg)]">
      <div className="border-b border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-3 pt-1">
        <Tabs
          size="small"
          activeKey={activeKey}
          onChange={setActiveService}
          className="[&>.ant-tabs-nav]:mb-0 [&>.ant-tabs-content-holder]:hidden"
          items={catalog.map((item) => {
            const count = selectedCount(item);
            return {
              key: item.name,
              label: count ? `${item.label} (${count})` : item.label,
            };
          })}
        />
      </div>
      <div className="max-h-[300px] overflow-auto p-3">
        {service ? (
          <div className="flex flex-col gap-2">
            <Checkbox
              checked={
                service.endpoints.length > 0
                && selectedCount(service) === service.endpoints.length
              }
              onChange={(event) => toggleService(service, event.target.checked)}
              className="font-medium text-[var(--color-text-1)]"
            >
              {service.kind === 'external'
                ? t('system.settings.secret.scopeExternal')
                : t('system.settings.secret.scopeSelectAll')}
            </Checkbox>
            {service.endpoints.map((endpoint) => (
              <label
                key={endpoint.key}
                className="flex items-start gap-2 rounded px-1 py-1 text-sm text-[var(--color-text-2)] hover:bg-[var(--color-fill-1)]"
              >
                <Checkbox
                  checked={selected.has(endpoint.key)}
                  onChange={(event) => toggle(endpoint.key, event.target.checked)}
                  className="mt-0.5"
                />
                <span className="min-w-0">
                  <span className="block font-mono text-xs text-[var(--color-text-1)]">
                    {endpoint.key}
                  </span>
                  {endpoint.label && endpoint.label !== endpoint.key ? (
                    <span className="block text-xs text-[var(--color-text-3)]">
                      {endpoint.label}
                    </span>
                  ) : null}
                </span>
              </label>
            ))}
          </div>
        ) : (
          <div className="py-6 text-center text-xs text-[var(--color-text-3)]">
            {t('system.settings.secret.scopeEmptyCatalog')}
          </div>
        )}
      </div>
    </div>
  );
};

const OpenApiTokenScopeFields: React.FC<OpenApiTokenScopeFieldsProps> = ({
  catalog,
}) => {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const watchedMode = Form.useWatch('scopeMode', form) as OpenApiTokenScopeMode | undefined;
  const scopeMode = watchedMode ?? form.getFieldValue('scopeMode');

  return (
    <>
      <Form.Item
        name="scopeMode"
        label={t('system.settings.secret.scope')}
        rules={[{ required: true, message: t('system.settings.secret.scopeRequired') }]}
      >
        <Radio.Group
          options={[
            { label: t('system.settings.secret.scopeAll'), value: 'all' },
            { label: t('system.settings.secret.scopeAllowlist'), value: 'allowlist' },
          ]}
        />
      </Form.Item>
      <Form.Item
        name="scopeEndpoints"
        hidden={scopeMode !== 'allowlist'}
        rules={[
          {
            validator: async (_, endpoints: string[]) => {
              if (scopeMode !== 'allowlist') {
                return;
              }
              if ((endpoints || []).length > 0) {
                return;
              }
              return Promise.reject(new Error(t('system.settings.secret.scopeRequired')));
            },
          },
        ]}
      >
        <EndpointPicker catalog={catalog} />
      </Form.Item>
    </>
  );
};

export default OpenApiTokenScopeFields;
