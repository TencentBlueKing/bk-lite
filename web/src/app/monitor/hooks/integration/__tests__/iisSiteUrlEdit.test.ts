import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { DataMapper } from '../useDataMapper';

type FormField = {
  name: string;
  editable?: boolean;
  transform_on_edit?:
    | string
    | {
        origin_path?: string;
        originPath?: string;
      };
};

const uiPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../../../../../server/apps/monitor/support-files/plugins/Telegraf/host/iis/UI.json',
);

const iisUi = JSON.parse(readFileSync(uiPath, 'utf8')) as {
  form_fields: FormField[];
};

const formFields = iisUi.form_fields;

const savedHttpResponse = () => ({
  child: {
    id: 'iis-http',
    content: {
      config: {
        urls: ['http://old.example.com/'],
        interval: '60s',
        insecure_skip_verify: true,
        response_timeout: '5s',
        tags: {
          config_type: ['win_perf_counters', 'http_response'],
        },
      },
    },
  },
});

// Same field loop as usePluginFromJson edit-mode getDefaultForm.
const getDefaultForm = (apiData: ReturnType<typeof savedHttpResponse>) => {
  const formValues: Record<string, unknown> = {};
  formFields.forEach((field) => {
    const { name, transform_on_edit } = field;
    if (transform_on_edit) {
      formValues[name] = DataMapper.transformValue(
        null,
        transform_on_edit,
        'toForm',
        apiData,
      );
    }
  });
  return formValues;
};

// Same field loop as usePluginFromJson edit-mode getParams.
const getParams = (
  formData: Record<string, unknown>,
  configForm: ReturnType<typeof savedHttpResponse>,
) => {
  const result = {
    ...configForm,
    child: {
      ...configForm.child,
      content: {
        ...configForm.child.content,
        config: {
          ...configForm.child.content.config,
        },
      },
    },
  };
  formFields.forEach((field) => {
    const { name, transform_on_edit, editable } = field;
    const formValue = formData[name];
    if (editable === false) {
      return;
    }
    if (formValue === undefined) {
      return;
    }
    if (!transform_on_edit) {
      return;
    }
    const transformedValue = DataMapper.transformValue(
      formValue,
      transform_on_edit,
      'toApi',
      undefined,
      formData,
    );
    if (transformedValue === undefined) {
      return;
    }
    const targetPath =
      typeof transform_on_edit === 'string'
        ? transform_on_edit
        : transform_on_edit.origin_path || transform_on_edit.originPath;
    if (targetPath) {
      DataMapper.setNestedValue(
        result,
        DataMapper.resolvePathVariables(targetPath, configForm),
        transformedValue,
      );
    }
  });
  return result;
};

describe('IIS http_response site URL edit mapping', () => {
  it('echoes saved urls[0] into the site URL field', () => {
    const saved = savedHttpResponse();
    const form = getDefaultForm(saved);

    expect(form.site_url).toBe('http://old.example.com/');
  });

  it('writes a new site URL back to urls[0] and keeps other mapped fields', () => {
    const saved = savedHttpResponse();
    const form = {
      ...getDefaultForm(saved),
      site_url: 'https://new.example.com/health',
      host: 'host-must-not-become-url.example.com',
    };
    const config = getParams(form, saved).child.content.config;

    expect(config.urls).toEqual(['https://new.example.com/health']);
    expect(config.urls[0]).not.toBe(form.host);
    expect(config.interval).toBe('60s');
    expect(config.insecure_skip_verify).toBe(true);
    expect(config.response_timeout).toBe('5s');
    expect(config.tags.config_type).toEqual(['win_perf_counters', 'http_response']);
  });

  it('does not let a host input replace urls', () => {
    const saved = savedHttpResponse();
    const form = {
      ...getDefaultForm(saved),
      site_url: 'http://old.example.com/',
      host: 'other-host.example.com',
    };
    const config = getParams(form, saved).child.content.config;

    expect(config.urls).toEqual(['http://old.example.com/']);
    expect(JSON.stringify(config)).not.toContain('other-host.example.com');
  });
});
