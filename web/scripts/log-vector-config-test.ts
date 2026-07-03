/**
 * Vector 采集"编辑模式"配置加载/保存一致性测试。
 *
 * 回归保护：当 `getDefaultForm` 改回旧的"从 content.sources.xxx 嵌套读取"模式时，
 * 以下测试会立即失败，避免再次出现"编辑时多行合并开关显示关闭"的 bug。
 *
 * 运行：`pnpm exec tsx scripts/log-vector-config-test.ts`
 */

import assert from 'node:assert/strict';
import {
  getVectorFileDefaultForm,
  getVectorFileParams
} from '../src/app/log/hooks/integration/collectors/vector/fileDefaults';
import {
  getVectorDockerDefaultForm,
  getVectorDockerParams
} from '../src/app/log/hooks/integration/collectors/vector/dockerDefaults';

// ============ file.tsx ============

// Case 1: 用户报告的核心 bug —— 已保存多行合并，编辑时开关应保持 ON
assert.deepEqual(
  getVectorFileDefaultForm({
    child: {
      content: {
        include: ['/var/log/xixi.log'],
        multiline: {
          mode: 'continue_through',
          start_pattern: '^\\d{4}-\\d{2}-\\d{2}',
          timeout_ms: 1000,
          condition_pattern: '\\s+'
        }
      }
    }
  }).multiline,
  {
    enabled: true,
    mode: 'continue_through',
    start_pattern: '^\\d{4}-\\d{2}-\\d{2}',
    timeout_ms: 1000,
    condition_pattern: '\\s+'
  },
  'file: 已保存 multiline 应在编辑时 enabled=true'
);

// Case 2: 未启用多行合并时，enabled 应为 false
assert.equal(
  getVectorFileDefaultForm({
    child: { content: { include: ['/var/log/x.log'] } }
  }).multiline.enabled,
  false,
  'file: 未保存 multiline 时 enabled 应为 false'
);

// Case 3: 完整往返 —— 保存多行合并 → 加载回来所有字段一致
{
  const form = {
    include: ['/var/log/a.log', '/var/log/b.log'],
    exclude: ['/var/log/a.log.gz'],
    read_from: 'end',
    ignore_older_secs: 3600,
    encoding_charset: 'gbk',
    parser_type: '',
    multiline: {
      enabled: true,
      mode: 'halt_before',
      start_pattern: '^ERROR',
      timeout_ms: 2000,
      condition_pattern: '^\\s'
    }
  };
  const params = getVectorFileParams(form, {});
  const loaded = getVectorFileDefaultForm({ child: params.child });
  assert.deepEqual(loaded, form, 'file: 完整往返一致性（多行合并 ON）');
}

// Case 4: 往返 —— 多行合并 OFF（输入包含完整默认，因为 defaultForm 总是返回完整结构）
{
  const form = {
    include: ['/var/log/c.log'],
    exclude: [],
    read_from: 'beginning',
    ignore_older_secs: 86400,
    encoding_charset: 'utf-8',
    parser_type: '',
    multiline: {
      enabled: false,
      mode: 'continue_through',
      start_pattern: '',
      timeout_ms: 1000,
      condition_pattern: ''
    }
  };
  const params = getVectorFileParams(form, {});
  const loaded = getVectorFileDefaultForm({ child: params.child });
  assert.equal(loaded.multiline.enabled, false, 'file: OFF 状态应保持');
  assert.deepEqual(loaded.include, form.include);
  assert.equal(loaded.read_from, form.read_from);
}

// Case 5: getParams 不会把 disabled 状态的 multiline 子字段写入 content
{
  const params = getVectorFileParams(
    {
      include: ['/x.log'],
      multiline: {
        enabled: false,
        mode: 'continue_through',
        start_pattern: '',
        timeout_ms: 1000,
        condition_pattern: ''
      }
    },
    {}
  );
  assert.equal(
    'multiline' in (params.child as Record<string, unknown>).content,
    false,
    'file: 禁用 multiline 时不应在 content 中保留 multiline 字段'
  );
}

// ============ docker.tsx ============

// Case 6: docker 多行合并开关已保存 → 编辑时 enabled=true
assert.deepEqual(
  getVectorDockerDefaultForm({
    child: {
      content: {
        enable_multiline: true,
        multiline_mode: 'continue_through',
        multiline_pattern: '\\s+',
        multiline_start_pattern: '^\\d{4}-\\d{2}-\\d{2}',
        multiline_timeout_ms: 1000
      }
    }
  }).multiline,
  {
    enabled: true,
    mode: 'continue_through',
    condition_pattern: '\\s+',
    start_pattern: '^\\d{4}-\\d{2}-\\d{2}',
    timeout_ms: 1000
  },
  'docker: 已保存多行合并应 enabled=true'
);

// Case 7: docker 未启用多行合并 → enabled=false
assert.equal(
  getVectorDockerDefaultForm({ child: { content: {} } }).multiline.enabled,
  false,
  'docker: 未保存 multiline 时 enabled 应为 false'
);

// Case 8: docker 容器过滤开关已保存 → enabled=true，数组正确还原
assert.deepEqual(
  getVectorDockerDefaultForm({
    child: {
      content: {
        enable_container_filter: true,
        container_name_contains: 'web, db ,cache',
        container_name_exclude: 'logspout'
      }
    }
  }),
  {
    endpoint: 'unix:///var/run/docker.sock',
    containerFilter: { enabled: true },
    container_name_contains: ['web', 'db', 'cache'],
    container_name_exclude: ['logspout'],
    multiline: {
      enabled: false,
      mode: 'continue_through',
      condition_pattern: '^[\\s]+',
      start_pattern: '^[^\\s]',
      timeout_ms: 1000
    }
  },
  'docker: 容器过滤开启时，CSV 字符串应正确 split 回数组并去空白'
);

// Case 9: docker 容器过滤关闭 → enabled=false，数组为 []
{
  const loaded = getVectorDockerDefaultForm({
    child: {
      content: {
        enable_container_filter: false,
        container_name_contains: '',
        container_name_exclude: ''
      }
    }
  });
  assert.equal(loaded.containerFilter.enabled, false);
  assert.deepEqual(loaded.container_name_contains, []);
  assert.deepEqual(loaded.container_name_exclude, []);
}

// Case 10: docker 完整往返（含容器过滤 + 多行合并 ON）
{
  const form = {
    endpoint: 'tcp://192.168.1.10:2375',
    containerFilter: { enabled: true },
    container_name_contains: ['nginx', 'app'],
    container_name_exclude: ['logspout', 'vector'],
    multiline: {
      enabled: true,
      mode: 'continue_past',
      condition_pattern: '^\\s',
      start_pattern: '^[A-Z]',
      timeout_ms: 1500
    }
  };
  const params = getVectorDockerParams(form, {});
  const loaded = getVectorDockerDefaultForm({ child: params.child });
  assert.deepEqual(loaded, form, 'docker: 完整往返一致性');
}

// Case 11: docker 完整往返（多行合并 OFF + 容器过滤 OFF）
{
  const form = {
    endpoint: 'unix:///var/run/docker.sock',
    containerFilter: { enabled: false },
    container_name_contains: [],
    container_name_exclude: ['vector', 'logspout'],
    multiline: {
      enabled: false,
      mode: 'continue_through',
      condition_pattern: '^[\\s]+',
      start_pattern: '^[^\\s]',
      timeout_ms: 1000
    }
  };
  const params = getVectorDockerParams(form, {});
  const loaded = getVectorDockerDefaultForm({ child: params.child });
  assert.equal(loaded.multiline.enabled, false, 'docker: multiline OFF');
  assert.equal(loaded.containerFilter.enabled, false, 'docker: 容器过滤 OFF');
  assert.deepEqual(
    loaded.container_name_exclude,
    ['vector', 'logspout'],
    'docker: 排除列表应保留'
  );
}

// Case 12: docker endpoint 自定义值不被默认值覆盖
{
  const loaded = getVectorDockerDefaultForm({
    child: { content: { endpoint: 'tcp://10.0.0.1:2376' } }
  });
  assert.equal(loaded.endpoint, 'tcp://10.0.0.1:2376');
}

console.log('log-vector-config tests passed: 12 cases');