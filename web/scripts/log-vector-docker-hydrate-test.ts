/**
 * Vector Docker 采集：编辑回填必须读解析后的 sources.docker_*。
 *
 * get_config_content 返回的是 docker.child.toml.j2 渲染并解析后的嵌套 TOML，
 * 自定义 docker_host / 容器数组 / multiline 在 sources.docker_<id> 上。
 * 只读扁平 endpoint/enable_* 会把端点打回 unix:///var/run/docker.sock，
 * 并把容器过滤、多行合并打成 false。
 *
 * 运行：
 * cd web && <tsx> scripts/log-vector-docker-hydrate-test.ts
 */

import assert from 'node:assert/strict';
import {
  getVectorDockerDefaultForm,
  getVectorDockerParams
} from '../src/app/log/hooks/integration/collectors/vector/dockerDefaults';

const DEFAULT_SOCKET = 'unix:///var/run/docker.sock';
const CUSTOM_HOST = 'tcp://192.168.1.10:2375';
const SOURCE_ID = 'docker_0198f0d7_1d4e_7db1_b7c2_132807fa330e';

const nestedFullContent = {
  sources: {
    [SOURCE_ID]: {
      type: 'docker_logs',
      docker_host: CUSTOM_HOST,
      auto_partial_merge: true,
      include_containers: ['nginx', 'app'],
      exclude_containers: ['logspout'],
      multiline: {
        condition_pattern: '^\\s',
        mode: 'continue_past',
        start_pattern: '^[A-Z]',
        timeout_ms: 1500
      }
    }
  }
};

// Case 1: nested sources.docker_* 必须回填自定义 docker_host / 过滤开 / 多行开
{
  const loaded = getVectorDockerDefaultForm({
    child: { content: nestedFullContent }
  });

  assert.equal(
    loaded.endpoint,
    CUSTOM_HOST,
    'nested docker_host 应回填到 endpoint，不能落到 unix:///var/run/docker.sock'
  );
  assert.notEqual(
    loaded.endpoint,
    DEFAULT_SOCKET,
    'nested 自定义 docker_host 不得被默认 socket 覆盖'
  );
  assert.equal(
    loaded.containerFilter.enabled,
    true,
    'nested 有 include/exclude 容器数组时容器过滤应开启'
  );
  assert.deepEqual(loaded.container_name_contains, ['nginx', 'app']);
  assert.deepEqual(loaded.container_name_exclude, ['logspout']);
  assert.equal(
    loaded.multiline.enabled,
    true,
    'nested 有 multiline 对象时多行合并应开启'
  );
  assert.equal(loaded.multiline.mode, 'continue_past');
  assert.equal(loaded.multiline.condition_pattern, '^\\s');
  assert.equal(loaded.multiline.start_pattern, '^[A-Z]');
  assert.equal(loaded.multiline.timeout_ms, 1500);
}

// Case 2: hydrate 后再 getVectorDockerParams，不得写回默认 socket 或把开关打成 false
{
  const loaded = getVectorDockerDefaultForm({
    child: { content: nestedFullContent }
  });
  const params = getVectorDockerParams(loaded, {});
  const saved = (params.child as { content: Record<string, unknown> }).content;

  assert.equal(
    saved.endpoint,
    CUSTOM_HOST,
    'roundtrip 保存的 endpoint 必须是自定义 docker_host，不能是默认 socket'
  );
  assert.notEqual(saved.endpoint, DEFAULT_SOCKET);
  assert.equal(
    saved.enable_container_filter,
    true,
    'roundtrip 不得把容器过滤写成 false'
  );
  assert.equal(
    saved.enable_multiline,
    true,
    'roundtrip 不得把多行合并写成 false'
  );
  assert.equal(saved.container_name_contains, 'nginx,app');
  assert.equal(saved.container_name_exclude, 'logspout');
  assert.equal(saved.multiline_mode, 'continue_past');
}

// Case 3: 无过滤字段 → 容器过滤关闭；缺字段不得当成默认排除列表
{
  const loaded = getVectorDockerDefaultForm({
    child: {
      content: {
        sources: {
          [SOURCE_ID]: {
            type: 'docker_logs',
            docker_host: CUSTOM_HOST,
            auto_partial_merge: true
          }
        }
      }
    }
  });

  assert.equal(loaded.endpoint, CUSTOM_HOST);
  assert.equal(
    loaded.containerFilter.enabled,
    false,
    '无 include_containers/exclude_containers 时容器过滤应关闭'
  );
  assert.deepEqual(
    loaded.container_name_contains,
    [],
    '无过滤字段时包含列表应为空'
  );
  assert.deepEqual(
    loaded.container_name_exclude,
    [],
    '无过滤字段时不得填入 vector,logspout 默认排除列表'
  );
  assert.equal(
    loaded.multiline.enabled,
    false,
    '无 multiline 时多行合并应关闭'
  );
}

// Case 4: 仅 include_containers，过滤开，排除列表为空
{
  const loaded = getVectorDockerDefaultForm({
    child: {
      content: {
        sources: {
          [SOURCE_ID]: {
            type: 'docker_logs',
            docker_host: CUSTOM_HOST,
            include_containers: ['web']
          }
        }
      }
    }
  });
  assert.equal(loaded.containerFilter.enabled, true);
  assert.deepEqual(loaded.container_name_contains, ['web']);
  assert.deepEqual(loaded.container_name_exclude, []);
}

// Case 5: 扁平 enable_* 结构保持兼容
{
  const loaded = getVectorDockerDefaultForm({
    child: {
      content: {
        endpoint: 'tcp://10.0.0.1:2376',
        enable_container_filter: true,
        container_name_contains: 'web, db',
        container_name_exclude: 'logspout',
        enable_multiline: true,
        multiline_mode: 'continue_through',
        multiline_pattern: '\\s+',
        multiline_start_pattern: '^\\d{4}',
        multiline_timeout_ms: 2000
      }
    }
  });

  assert.equal(loaded.endpoint, 'tcp://10.0.0.1:2376');
  assert.equal(loaded.containerFilter.enabled, true);
  assert.deepEqual(loaded.container_name_contains, ['web', 'db']);
  assert.deepEqual(loaded.container_name_exclude, ['logspout']);
  assert.equal(loaded.multiline.enabled, true);
  assert.equal(loaded.multiline.mode, 'continue_through');
  assert.equal(loaded.multiline.condition_pattern, '\\s+');
  assert.equal(loaded.multiline.start_pattern, '^\\d{4}');
  assert.equal(loaded.multiline.timeout_ms, 2000);
}

// Case 6: 扁平无开关字段时过滤/多行关闭
{
  const loaded = getVectorDockerDefaultForm({
    child: { content: { endpoint: CUSTOM_HOST } }
  });
  assert.equal(loaded.endpoint, CUSTOM_HOST);
  assert.equal(loaded.containerFilter.enabled, false);
  assert.equal(loaded.multiline.enabled, false);
}

console.log('log-vector-docker-hydrate tests passed');
