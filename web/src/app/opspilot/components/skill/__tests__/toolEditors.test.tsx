import React, { act, createRef } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ElasticsearchToolEditor from '../elasticsearchToolEditor';
import JenkinsToolEditor from '../jenkinsToolEditor';
import KubernetesToolEditor from '../kubernetesToolEditor';
import MssqlToolEditor from '../mssqlToolEditor';
import MysqlToolEditor from '../mysqlToolEditor';
import OracleToolEditor from '../oracleToolEditor';
import PostgresToolEditor from '../postgresToolEditor';
import RedisToolEditor from '../redisToolEditor';
import { parseRedisToolConfig } from '../redisToolEditor';
import type { ToolVariable } from '@/app/opspilot/types/tool';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const { skillApiMocks } = vi.hoisted(() => ({
  skillApiMocks: {
    testRedisConnection: vi.fn().mockResolvedValue(undefined),
    testMysqlConnection: vi.fn().mockResolvedValue(undefined),
    testPostgresConnection: vi.fn().mockResolvedValue(undefined),
    testOracleConnection: vi.fn().mockResolvedValue(undefined),
    testMssqlConnection: vi.fn().mockResolvedValue(undefined),
    testEsConnection: vi.fn().mockResolvedValue(undefined),
    testJenkinsConnection: vi.fn().mockResolvedValue(undefined),
    testKubernetesConnection: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock('@/app/opspilot/api/skill', () => ({ useSkillApi: () => skillApiMocks }));

vi.mock('@/app/opspilot/components/opspilot-tool-editor/tool-connection-status-tag', () => ({
  default: ({ status }: { status: string }) => <span data-testid="connection-status">{status}</span>,
}));

interface SaveHandle {
  save: () => boolean;
}

interface EditorProps {
  initialKwargs: ToolVariable[];
  onSave: (kwargs: ToolVariable[]) => void;
}

type EditorComponent = React.ForwardRefExoticComponent<EditorProps & React.RefAttributes<SaveHandle>>;

interface EditorCase {
  name: string;
  Component: EditorComponent;
  instancesKey: string;
  defaultInstanceIdKey?: string;
  instance: Record<string, unknown>;
  trimmedField: string;
  trimmedValue: string;
  testButton: string;
  testMethod: keyof typeof skillApiMocks;
}

const editorCases: EditorCase[] = [
  {
    name: 'Redis', Component: RedisToolEditor, instancesKey: 'redis_instances',
    defaultInstanceIdKey: 'redis_default_instance_id',
    instance: { id: 'redis-1', name: ' Redis Production ', url: ' redis://localhost:6379 ' },
    trimmedField: 'url', trimmedValue: 'redis://localhost:6379',
    testButton: 'tool.redis.testConnection', testMethod: 'testRedisConnection',
  },
  {
    name: 'MySQL', Component: MysqlToolEditor, instancesKey: 'mysql_instances',
    defaultInstanceIdKey: 'mysql_default_instance_id',
    instance: { id: 'mysql-1', name: ' MySQL Production ', host: ' mysql.local ' },
    trimmedField: 'host', trimmedValue: 'mysql.local',
    testButton: 'tool.mysql.testConnection', testMethod: 'testMysqlConnection',
  },
  {
    name: 'PostgreSQL', Component: PostgresToolEditor, instancesKey: 'postgres_instances',
    defaultInstanceIdKey: 'postgres_default_instance_id',
    instance: { id: 'postgres-1', name: ' PostgreSQL Production ', host: ' postgres.local ' },
    trimmedField: 'host', trimmedValue: 'postgres.local',
    testButton: 'tool.postgres.testConnection', testMethod: 'testPostgresConnection',
  },
  {
    name: 'Oracle', Component: OracleToolEditor, instancesKey: 'oracle_instances',
    defaultInstanceIdKey: 'oracle_default_instance_id',
    instance: { id: 'oracle-1', name: ' Oracle Production ', host: ' oracle.local ' },
    trimmedField: 'host', trimmedValue: 'oracle.local',
    testButton: 'tool.oracle.testConnection', testMethod: 'testOracleConnection',
  },
  {
    name: 'MSSQL', Component: MssqlToolEditor, instancesKey: 'mssql_instances',
    defaultInstanceIdKey: 'mssql_default_instance_id',
    instance: { id: 'mssql-1', name: ' MSSQL Production ', host: ' mssql.local ' },
    trimmedField: 'host', trimmedValue: 'mssql.local',
    testButton: 'tool.mssql.testConnection', testMethod: 'testMssqlConnection',
  },
  {
    name: 'Elasticsearch', Component: ElasticsearchToolEditor, instancesKey: 'es_instances',
    defaultInstanceIdKey: 'es_default_instance_id',
    instance: { id: 'es-1', name: ' Elasticsearch Production ', url: ' http://es.local:9200 ' },
    trimmedField: 'url', trimmedValue: 'http://es.local:9200',
    testButton: 'tool.elasticsearch.testConnection', testMethod: 'testEsConnection',
  },
  {
    name: 'Jenkins', Component: JenkinsToolEditor, instancesKey: 'jenkins_instances',
    defaultInstanceIdKey: 'jenkins_default_instance_id',
    instance: { id: 'jenkins-1', name: ' Jenkins Production ', jenkins_url: ' http://jenkins.local ' },
    trimmedField: 'jenkins_url', trimmedValue: 'http://jenkins.local',
    testButton: 'tool.jenkins.testConnection', testMethod: 'testJenkinsConnection',
  },
  {
    name: 'Kubernetes', Component: KubernetesToolEditor, instancesKey: 'kubernetes_instances',
    instance: { id: 'kubernetes-1', name: ' Kubernetes Production ', kubeconfig_data: ' apiVersion: v1\nclusters: [] ' },
    trimmedField: 'kubeconfig_data', trimmedValue: 'apiVersion: v1\nclusters: []',
    testButton: 'tool.kubernetes.testConnection', testMethod: 'testKubernetesConnection',
  },
];

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe.each(editorCases)('$name tool editor', ({
  Component, instancesKey, defaultInstanceIdKey, instance, trimmedField, trimmedValue,
}) => {
  it('通过统一 save 接口校验并序列化自身配置', () => {
    const ref = createRef<SaveHandle>();
    const onSave = vi.fn<(kwargs: ToolVariable[]) => void>();
    render(
      <Component
        ref={ref}
        initialKwargs={[{ key: instancesKey, value: JSON.stringify([instance]) }]}
        onSave={onSave}
      />,
    );

    let saved = false;
    act(() => { saved = ref.current?.save() ?? false; });

    expect(saved).toBe(true);
    expect(onSave).toHaveBeenCalledOnce();
    const savedKwargs = onSave.mock.calls[0][0];
    const instancesValue = savedKwargs.find(({ key }) => key === instancesKey)?.value;
    expect(typeof instancesValue).toBe('string');
    const savedInstances = JSON.parse(String(instancesValue)) as Record<string, unknown>[];
    expect(savedInstances).toHaveLength(1);
    expect(savedInstances[0]).toMatchObject({
      id: instance.id,
      name: String(instance.name).trim(),
      [trimmedField]: trimmedValue,
    });
    expect(savedInstances[0]).not.toHaveProperty('testStatus');

    if (defaultInstanceIdKey) {
      expect(savedKwargs).toContainEqual({ key: defaultInstanceIdKey, value: instance.id });
    }
  });
});

describe.each(editorCases)('$name tool editor connection test', ({
  Component, instancesKey, instance, testButton, testMethod,
}) => {
  it('只把当前实例交给对应连接 API，并独立更新测试状态', async () => {
    const ref = createRef<SaveHandle>();
    render(
      <Component
        ref={ref}
        initialKwargs={[{ key: instancesKey, value: JSON.stringify([instance]) }]}
        onSave={vi.fn()}
      />,
    );

    expect(screen.getByTestId('connection-status').textContent).toBe('untested');
    fireEvent.click(screen.getByText(testButton));

    await waitFor(() => expect(skillApiMocks[testMethod]).toHaveBeenCalledOnce());
    const payload = skillApiMocks[testMethod].mock.calls[0][0] as Record<string, unknown>;
    expect(payload).toMatchObject({ id: instance.id, name: instance.name });
    expect(payload).not.toHaveProperty('testStatus');
    await waitFor(() => expect(screen.getByTestId('connection-status').textContent).toBe('success'));
  });
});

describe('Redis 旧单实例配置兼容', () => {
  it('读取旧字段并在保存时升级为多实例协议', () => {
    const legacyKwargs: ToolVariable[] = [
      { key: 'url', value: 'redis://legacy.local:6379' },
      { key: 'username', value: 'legacy-user' },
      { key: 'ssl', value: 'true' },
      { key: 'cluster_mode', value: '1' },
    ];
    expect(parseRedisToolConfig(legacyKwargs)).toMatchObject([{
      id: 'redis-1',
      name: 'Redis - 1',
      url: 'redis://legacy.local:6379',
      username: 'legacy-user',
      ssl: true,
      cluster_mode: true,
      testStatus: 'untested',
    }]);

    const ref = createRef<SaveHandle>();
    const onSave = vi.fn<(kwargs: ToolVariable[]) => void>();
    render(<RedisToolEditor ref={ref} initialKwargs={legacyKwargs} onSave={onSave} />);
    act(() => { ref.current?.save(); });

    const upgraded = onSave.mock.calls[0][0];
    expect(upgraded.find(({ key }) => key === 'redis_default_instance_id')?.value).toBe('redis-1');
    const instancesValue = upgraded.find(({ key }) => key === 'redis_instances')?.value;
    expect(JSON.parse(String(instancesValue))).toMatchObject([{
      id: 'redis-1',
      url: 'redis://legacy.local:6379',
      username: 'legacy-user',
      ssl: true,
      cluster_mode: true,
    }]);
  });
});

describe('连接失败反馈', () => {
  it('连接 API 拒绝时只把当前实例标记为失败', async () => {
    skillApiMocks.testRedisConnection.mockRejectedValueOnce(new Error('connection refused'));
    render(
      <RedisToolEditor
        ref={createRef<SaveHandle>()}
        initialKwargs={[{
          key: 'redis_instances',
          value: JSON.stringify([{ id: 'redis-failed', name: 'Redis Failed', url: 'redis://failed.local:6379' }]),
        }]}
        onSave={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText('tool.redis.testConnection'));

    await waitFor(() => expect(skillApiMocks.testRedisConnection).toHaveBeenCalledOnce());
    await waitFor(() => expect(screen.getByTestId('connection-status').textContent).toBe('failed'));
  });
});
