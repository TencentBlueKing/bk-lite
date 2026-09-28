import { describe, expect, it } from 'vitest';

import {
  createFormFieldSchema,
  formFieldWidget,
} from '../lib/form-field-registry';

describe('编排表单字段注册表', () => {
  it('为资源和文件生成完整结构契约', () => {
    const target = createFormFieldSchema('target-selector', '目标主机');
    const file = createFormFieldSchema('file-upload', '报告模板');

    expect(target).toMatchObject({
      type: 'array',
      'x-widget': 'target-selector',
      'x-target-binding': {
        mode: 'runtime',
        allowedSources: ['node_mgmt', 'job_mgmt'],
        minCount: 1,
        maxCount: 100,
      },
    });
    expect(file).toMatchObject({
      type: 'object',
      'x-widget': 'file-upload',
      'x-file-options': {
        accept: ['docx', 'xlsx'],
        maxSizeMiB: 5,
        sourceModes: ['upload'],
      },
    });
    expect(formFieldWidget(target)).toBe('target-selector');
  });
});
