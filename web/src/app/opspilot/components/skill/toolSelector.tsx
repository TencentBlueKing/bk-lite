import React, { useState, useEffect } from 'react';
import { Button, Tooltip, Form, Input, Empty, InputNumber, Switch, message } from 'antd';

const { TextArea } = Input;
import { DeleteOutlined, EditOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import SelectorOperateModal from './operateModal';
import Icon from '@/components/icon';
import styles from './index.module.scss';
import { SelectTool, ToolVariable } from '@/app/opspilot/types/tool';
import { useSkillApi } from '@/app/opspilot/api/skill';
import OperateModal from '@/components/operate-modal';
import EditablePasswordField from '@/components/dynamic-form/editPasswordField';
import GroupTreeSelect from '@/components/group-tree-select';
import RedisToolEditor, { RedisInstanceFormValue } from './redisToolEditor';
import MysqlToolEditor, { MysqlInstanceFormValue } from './mysqlToolEditor';
import OracleToolEditor, { OracleInstanceFormValue } from './oracleToolEditor';
import MssqlToolEditor, { MssqlInstanceFormValue } from './mssqlToolEditor';
import PostgresToolEditor, { PostgresInstanceFormValue } from './postgresToolEditor';
import ElasticsearchToolEditor, { ElasticsearchInstanceFormValue } from './elasticsearchToolEditor';
import JenkinsToolEditor, { JenkinsInstanceFormValue } from './jenkinsToolEditor';
import KubernetesToolEditor, { KubernetesInstanceFormValue } from './kubernetesToolEditor';

const REDIS_TOOL_NAME = 'redis';
const REDIS_INSTANCES_KEY = 'redis_instances';
const REDIS_DEFAULT_INSTANCE_ID_KEY = 'redis_default_instance_id';
const REDIS_AUTO_NAME_PREFIX = 'Redis - ';

const createRedisInstanceId = () => `redis-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const getDefaultRedisInstance = (name: string): RedisInstanceFormValue => ({
  id: createRedisInstanceId(),
  name,
  url: '',
  username: '',
  password: '',
  ssl: false,
  ssl_ca_path: '',
  ssl_keyfile: '',
  ssl_certfile: '',
  ssl_cert_reqs: '',
  ssl_ca_certs: '',
  cluster_mode: false,
  testStatus: 'untested',
});

const getNextRedisInstanceName = (instances: RedisInstanceFormValue[]) => {
  const maxIndex = instances.reduce((max, instance) => {
    const match = instance.name.match(/^Redis - (\d+)$/);
    if (!match) {
      return max;
    }
    return Math.max(max, Number(match[1]));
  }, 0);
  return `${REDIS_AUTO_NAME_PREFIX}${maxIndex + 1}`;
};

const parseRedisInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) {
    return value as Record<string, unknown>[];
  }
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
};

const parseRedisBoolean = (value: unknown) => {
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'string') {
    return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase());
  }
  return Boolean(value);
};

const parseRedisToolConfig = (kwargs: ToolVariable[] = []): RedisInstanceFormValue[] => {
  const kwargsMap = new Map(kwargs.filter((item) => item.key).map((item) => [item.key, item.value]));
  const instancesValue = kwargsMap.get(REDIS_INSTANCES_KEY);
  const parsedInstances = parseRedisInstancesValue(instancesValue);

  if (parsedInstances.length > 0) {
    return parsedInstances.map((item, index) => ({
      id: String(item.id || `redis-${index + 1}`),
      name: String(item.name || `${REDIS_AUTO_NAME_PREFIX}${index + 1}`),
      url: String(item.url || ''),
      username: String(item.username || ''),
      password: String(item.password || ''),
      ssl: parseRedisBoolean(item.ssl),
      ssl_ca_path: String(item.ssl_ca_path || ''),
      ssl_keyfile: String(item.ssl_keyfile || ''),
      ssl_certfile: String(item.ssl_certfile || ''),
      ssl_cert_reqs: String(item.ssl_cert_reqs || ''),
      ssl_ca_certs: String(item.ssl_ca_certs || ''),
      cluster_mode: parseRedisBoolean(item.cluster_mode),
      testStatus: 'untested',
    }));
  }

  const hasLegacyConfig = ['url', 'username', 'password', 'ssl', 'ssl_ca_path', 'ssl_keyfile', 'ssl_certfile', 'ssl_cert_reqs', 'ssl_ca_certs', 'cluster_mode']
    .some((key) => kwargsMap.has(key));

  if (hasLegacyConfig) {
    return [{
      id: 'redis-1',
      name: 'Redis - 1',
      url: String(kwargsMap.get('url') || ''),
      username: String(kwargsMap.get('username') || ''),
      password: String(kwargsMap.get('password') || ''),
      ssl: parseRedisBoolean(kwargsMap.get('ssl')),
      ssl_ca_path: String(kwargsMap.get('ssl_ca_path') || ''),
      ssl_keyfile: String(kwargsMap.get('ssl_keyfile') || ''),
      ssl_certfile: String(kwargsMap.get('ssl_certfile') || ''),
      ssl_cert_reqs: String(kwargsMap.get('ssl_cert_reqs') || ''),
      ssl_ca_certs: String(kwargsMap.get('ssl_ca_certs') || ''),
      cluster_mode: parseRedisBoolean(kwargsMap.get('cluster_mode')),
      testStatus: 'untested',
    }];
  }

  return [getDefaultRedisInstance('Redis - 1')];
};

const serializeRedisToolConfig = (instances: RedisInstanceFormValue[]): ToolVariable[] => {
  const normalizedInstances = instances.map((instance) => {
    const normalizedInstance = { ...instance };
    delete normalizedInstance.testStatus;
    return normalizedInstance;
  });
  return [
    { key: REDIS_INSTANCES_KEY, value: JSON.stringify(normalizedInstances) },
    { key: REDIS_DEFAULT_INSTANCE_ID_KEY, value: normalizedInstances[0]?.id || '' },
  ];
};

const isRedisTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === REDIS_TOOL_NAME;

const MYSQL_TOOL_NAME = 'mysql';
const MYSQL_INSTANCES_KEY = 'mysql_instances';
const MYSQL_DEFAULT_INSTANCE_ID_KEY = 'mysql_default_instance_id';
const MYSQL_AUTO_NAME_PREFIX = 'MySQL - ';

const createMysqlInstanceId = () => `mysql-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const getDefaultMysqlInstance = (name: string): MysqlInstanceFormValue => ({
  id: createMysqlInstanceId(),
  name,
  host: '',
  port: 3306,
  database: '',
  user: '',
  password: '',
  charset: 'utf8mb4',
  collation: 'utf8mb4_unicode_ci',
  ssl: false,
  ssl_ca: '',
  ssl_cert: '',
  ssl_key: '',
  testStatus: 'untested',
});

const getNextMysqlInstanceName = (instances: MysqlInstanceFormValue[]) => {
  const maxIndex = instances.reduce((max, instance) => {
    const match = instance.name.match(/^MySQL - (\d+)$/);
    if (!match) {
      return max;
    }
    return Math.max(max, Number(match[1]));
  }, 0);
  return `${MYSQL_AUTO_NAME_PREFIX}${maxIndex + 1}`;
};

const parseMysqlInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) {
    return value as Record<string, unknown>[];
  }
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
};

const parseMysqlBoolean = (value: unknown) => {
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'string') {
    return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase());
  }
  return Boolean(value);
};

const parseMysqlInt = (value: unknown, defaultValue: number) => {
  if (typeof value === 'number') {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = parseInt(value, 10);
    return isNaN(parsed) ? defaultValue : parsed;
  }
  return defaultValue;
};

const parseMysqlToolConfig = (kwargs: ToolVariable[] = []): MysqlInstanceFormValue[] => {
  const kwargsMap = new Map(kwargs.filter((item) => item.key).map((item) => [item.key, item.value]));
  const instancesValue = kwargsMap.get(MYSQL_INSTANCES_KEY);
  const parsedInstances = parseMysqlInstancesValue(instancesValue);

  if (parsedInstances.length > 0) {
    return parsedInstances.map((item, index) => ({
      id: String(item.id || `mysql-${index + 1}`),
      name: String(item.name || `${MYSQL_AUTO_NAME_PREFIX}${index + 1}`),
      host: String(item.host || ''),
      port: parseMysqlInt(item.port, 3306),
      database: String(item.database || ''),
      user: String(item.user || ''),
      password: String(item.password || ''),
      charset: String(item.charset || 'utf8mb4'),
      collation: String(item.collation || 'utf8mb4_unicode_ci'),
      ssl: parseMysqlBoolean(item.ssl),
      ssl_ca: String(item.ssl_ca || ''),
      ssl_cert: String(item.ssl_cert || ''),
      ssl_key: String(item.ssl_key || ''),
      testStatus: 'untested',
    }));
  }

  const hasLegacyConfig = ['host', 'port', 'database', 'user', 'password']
    .some((key) => kwargsMap.has(key));

  if (hasLegacyConfig) {
    return [{
      id: 'mysql-1',
      name: 'MySQL - 1',
      host: String(kwargsMap.get('host') || ''),
      port: parseMysqlInt(kwargsMap.get('port'), 3306),
      database: String(kwargsMap.get('database') || ''),
      user: String(kwargsMap.get('user') || ''),
      password: String(kwargsMap.get('password') || ''),
      charset: String(kwargsMap.get('charset') || 'utf8mb4'),
      collation: String(kwargsMap.get('collation') || 'utf8mb4_unicode_ci'),
      ssl: parseMysqlBoolean(kwargsMap.get('ssl')),
      ssl_ca: String(kwargsMap.get('ssl_ca') || ''),
      ssl_cert: String(kwargsMap.get('ssl_cert') || ''),
      ssl_key: String(kwargsMap.get('ssl_key') || ''),
      testStatus: 'untested',
    }];
  }

  return [getDefaultMysqlInstance('MySQL - 1')];
};

const serializeMysqlToolConfig = (instances: MysqlInstanceFormValue[]): ToolVariable[] => {
  const normalizedInstances = instances.map((instance) => {
    const normalizedInstance = { ...instance };
    delete normalizedInstance.testStatus;
    return normalizedInstance;
  });
  return [
    { key: MYSQL_INSTANCES_KEY, value: JSON.stringify(normalizedInstances) },
    { key: MYSQL_DEFAULT_INSTANCE_ID_KEY, value: normalizedInstances[0]?.id || '' },
  ];
};

const isMysqlTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === MYSQL_TOOL_NAME;

const ORACLE_TOOL_NAME = 'oracle';
const ORACLE_INSTANCES_KEY = 'oracle_instances';
const ORACLE_DEFAULT_INSTANCE_ID_KEY = 'oracle_default_instance_id';
const ORACLE_AUTO_NAME_PREFIX = 'Oracle - ';

const createOracleInstanceId = () => `oracle-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const getDefaultOracleInstance = (name: string): OracleInstanceFormValue => ({
  id: createOracleInstanceId(),
  name,
  host: '',
  port: 1521,
  service_name: '',
  user: '',
  password: '',
  nls_lang: '',
  testStatus: 'untested',
});

const getNextOracleInstanceName = (instances: OracleInstanceFormValue[]) => {
  const maxIndex = instances.reduce((max, instance) => {
    const match = instance.name.match(/^Oracle - (\d+)$/);
    if (!match) {
      return max;
    }
    return Math.max(max, Number(match[1]));
  }, 0);
  return `${ORACLE_AUTO_NAME_PREFIX}${maxIndex + 1}`;
};

const parseOracleInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) {
    return value as Record<string, unknown>[];
  }
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
};

const parseOracleInt = (value: unknown, defaultValue: number) => {
  if (typeof value === 'number') {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = parseInt(value, 10);
    return isNaN(parsed) ? defaultValue : parsed;
  }
  return defaultValue;
};

const parseOracleToolConfig = (kwargs: ToolVariable[] = []): OracleInstanceFormValue[] => {
  const kwargsMap = new Map(kwargs.filter((item) => item.key).map((item) => [item.key, item.value]));
  const instancesValue = kwargsMap.get(ORACLE_INSTANCES_KEY);
  const parsedInstances = parseOracleInstancesValue(instancesValue);

  if (parsedInstances.length > 0) {
    return parsedInstances.map((item, index) => ({
      id: String(item.id || `oracle-${index + 1}`),
      name: String(item.name || `${ORACLE_AUTO_NAME_PREFIX}${index + 1}`),
      host: String(item.host || ''),
      port: parseOracleInt(item.port, 1521),
      service_name: String(item.service_name || ''),
      user: String(item.user || ''),
      password: String(item.password || ''),
      nls_lang: String(item.nls_lang || ''),
      testStatus: 'untested',
    }));
  }

  const hasLegacyConfig = ['host', 'port', 'service_name', 'user', 'password']
    .some((key) => kwargsMap.has(key));

  if (hasLegacyConfig) {
    return [{
      id: 'oracle-1',
      name: 'Oracle - 1',
      host: String(kwargsMap.get('host') || ''),
      port: parseOracleInt(kwargsMap.get('port'), 1521),
      service_name: String(kwargsMap.get('service_name') || ''),
      user: String(kwargsMap.get('user') || ''),
      password: String(kwargsMap.get('password') || ''),
      nls_lang: String(kwargsMap.get('nls_lang') || ''),
      testStatus: 'untested',
    }];
  }

  return [getDefaultOracleInstance('Oracle - 1')];
};

const serializeOracleToolConfig = (instances: OracleInstanceFormValue[]): ToolVariable[] => {
  const normalizedInstances = instances.map((instance) => {
    const normalizedInstance = { ...instance };
    delete normalizedInstance.testStatus;
    return normalizedInstance;
  });
  return [
    { key: ORACLE_INSTANCES_KEY, value: JSON.stringify(normalizedInstances) },
    { key: ORACLE_DEFAULT_INSTANCE_ID_KEY, value: normalizedInstances[0]?.id || '' },
  ];
};

const isOracleTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === ORACLE_TOOL_NAME;

const MSSQL_TOOL_NAME = 'mssql';
const MONITOR_TOOL_NAME = 'monitor';
const MSSQL_INSTANCES_KEY = 'mssql_instances';
const MSSQL_DEFAULT_INSTANCE_ID_KEY = 'mssql_default_instance_id';
const MSSQL_AUTO_NAME_PREFIX = 'MSSQL - ';

const createMssqlInstanceId = () => `mssql-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const getDefaultMssqlInstance = (name: string): MssqlInstanceFormValue => ({
  id: createMssqlInstanceId(),
  name,
  host: '',
  port: 1433,
  database: 'master',
  user: '',
  password: '',
  testStatus: 'untested',
});

const getNextMssqlInstanceName = (instances: MssqlInstanceFormValue[]) => {
  const maxIndex = instances.reduce((max, instance) => {
    const match = instance.name.match(/^MSSQL - (\d+)$/);
    if (!match) {
      return max;
    }
    return Math.max(max, Number(match[1]));
  }, 0);
  return `${MSSQL_AUTO_NAME_PREFIX}${maxIndex + 1}`;
};

const parseMssqlInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) {
    return value as Record<string, unknown>[];
  }
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
};

const parseMssqlInt = (value: unknown, defaultValue: number) => {
  if (typeof value === 'number') {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = parseInt(value, 10);
    return isNaN(parsed) ? defaultValue : parsed;
  }
  return defaultValue;
};

const parseMssqlToolConfig = (kwargs: ToolVariable[] = []): MssqlInstanceFormValue[] => {
  const kwargsMap = new Map(kwargs.filter((item) => item.key).map((item) => [item.key, item.value]));
  const instancesValue = kwargsMap.get(MSSQL_INSTANCES_KEY);
  const parsedInstances = parseMssqlInstancesValue(instancesValue);

  if (parsedInstances.length > 0) {
    return parsedInstances.map((item, index) => ({
      id: String(item.id || `mssql-${index + 1}`),
      name: String(item.name || `${MSSQL_AUTO_NAME_PREFIX}${index + 1}`),
      host: String(item.host || ''),
      port: parseMssqlInt(item.port, 1433),
      database: String(item.database || 'master'),
      user: String(item.user || ''),
      password: String(item.password || ''),
      testStatus: 'untested',
    }));
  }

  const hasLegacyConfig = ['host', 'port', 'database', 'user', 'password']
    .some((key) => kwargsMap.has(key));

  if (hasLegacyConfig) {
    return [{
      id: 'mssql-1',
      name: 'MSSQL - 1',
      host: String(kwargsMap.get('host') || ''),
      port: parseMssqlInt(kwargsMap.get('port'), 1433),
      database: String(kwargsMap.get('database') || 'master'),
      user: String(kwargsMap.get('user') || ''),
      password: String(kwargsMap.get('password') || ''),
      testStatus: 'untested',
    }];
  }

  return [getDefaultMssqlInstance('MSSQL - 1')];
};

const serializeMssqlToolConfig = (instances: MssqlInstanceFormValue[]): ToolVariable[] => {
  const normalizedInstances = instances.map((instance) => {
    const normalizedInstance = { ...instance };
    delete normalizedInstance.testStatus;
    return normalizedInstance;
  });
  return [
    { key: MSSQL_INSTANCES_KEY, value: JSON.stringify(normalizedInstances) },
    { key: MSSQL_DEFAULT_INSTANCE_ID_KEY, value: normalizedInstances[0]?.id || '' },
  ];
};

const isMssqlTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === MSSQL_TOOL_NAME;
const isMonitorTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === MONITOR_TOOL_NAME;

// ── PostgreSQL ────────────────────────────────────────────────────────────────

const POSTGRES_TOOL_NAME = 'postgres';
const POSTGRES_INSTANCES_KEY = 'postgres_instances';
const POSTGRES_DEFAULT_INSTANCE_ID_KEY = 'postgres_default_instance_id';
const POSTGRES_AUTO_NAME_PREFIX = 'PostgreSQL - ';

const createPostgresInstanceId = () => `postgres-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const getDefaultPostgresInstance = (name: string): PostgresInstanceFormValue => ({
  id: createPostgresInstanceId(),
  name,
  host: '',
  port: 5432,
  database: 'postgres',
  user: '',
  password: '',
  testStatus: 'untested',
});

const getNextPostgresInstanceName = (instances: PostgresInstanceFormValue[]) => {
  const maxIndex = instances.reduce((max, instance) => {
    const match = instance.name.match(/^PostgreSQL - (\d+)$/);
    if (!match) return max;
    return Math.max(max, Number(match[1]));
  }, 0);
  return `${POSTGRES_AUTO_NAME_PREFIX}${maxIndex + 1}`;
};

const parsePostgresInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) return value as Record<string, unknown>[];
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch { return []; }
  }
  return [];
};

const parsePostgresInt = (value: unknown, defaultValue: number) => {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const parsed = parseInt(value, 10);
    return isNaN(parsed) ? defaultValue : parsed;
  }
  return defaultValue;
};

const parsePostgresToolConfig = (kwargs: ToolVariable[] = []): PostgresInstanceFormValue[] => {
  const kwargsMap = new Map(kwargs.filter((item) => item.key).map((item) => [item.key, item.value]));
  const instancesValue = kwargsMap.get(POSTGRES_INSTANCES_KEY);
  const parsedInstances = parsePostgresInstancesValue(instancesValue);

  if (parsedInstances.length > 0) {
    return parsedInstances.map((item, index) => ({
      id: String(item.id || `postgres-${index + 1}`),
      name: String(item.name || `${POSTGRES_AUTO_NAME_PREFIX}${index + 1}`),
      host: String(item.host || ''),
      port: parsePostgresInt(item.port, 5432),
      database: String(item.database || 'postgres'),
      user: String(item.user || ''),
      password: String(item.password || ''),
      testStatus: 'untested',
    }));
  }

  const hasLegacyConfig = ['host', 'port', 'database', 'user', 'password'].some((key) => kwargsMap.has(key));
  if (hasLegacyConfig) {
    return [{
      id: 'postgres-1',
      name: 'PostgreSQL - 1',
      host: String(kwargsMap.get('host') || ''),
      port: parsePostgresInt(kwargsMap.get('port'), 5432),
      database: String(kwargsMap.get('database') || 'postgres'),
      user: String(kwargsMap.get('user') || ''),
      password: String(kwargsMap.get('password') || ''),
      testStatus: 'untested',
    }];
  }

  return [getDefaultPostgresInstance('PostgreSQL - 1')];
};

const serializePostgresToolConfig = (instances: PostgresInstanceFormValue[]): ToolVariable[] => {
  const normalized = instances.map((instance) => {
    const copy = { ...instance };
    delete copy.testStatus;
    return copy;
  });
  return [
    { key: POSTGRES_INSTANCES_KEY, value: JSON.stringify(normalized) },
    { key: POSTGRES_DEFAULT_INSTANCE_ID_KEY, value: normalized[0]?.id || '' },
  ];
};

const isPostgresTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === POSTGRES_TOOL_NAME;

// ── Elasticsearch ─────────────────────────────────────────────────────────────

const ES_TOOL_NAME = 'elasticsearch';
const ES_INSTANCES_KEY = 'es_instances';
const ES_DEFAULT_INSTANCE_ID_KEY = 'es_default_instance_id';
const ES_AUTO_NAME_PREFIX = 'Elasticsearch - ';

const createEsInstanceId = () => `es-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const getDefaultEsInstance = (name: string): ElasticsearchInstanceFormValue => ({
  id: createEsInstanceId(),
  name,
  url: '',
  username: '',
  password: '',
  api_key: '',
  verify_certs: true,
  testStatus: 'untested',
});

const getNextEsInstanceName = (instances: ElasticsearchInstanceFormValue[]) => {
  const maxIndex = instances.reduce((max, instance) => {
    const match = instance.name.match(/^Elasticsearch - (\d+)$/);
    if (!match) return max;
    return Math.max(max, Number(match[1]));
  }, 0);
  return `${ES_AUTO_NAME_PREFIX}${maxIndex + 1}`;
};

const parseEsInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) return value as Record<string, unknown>[];
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch { return []; }
  }
  return [];
};

const parseEsBoolean = (value: unknown, defaultValue = true) => {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') return !['false', '0', 'no', 'off'].includes(value.toLowerCase());
  return defaultValue;
};

const parseEsToolConfig = (kwargs: ToolVariable[] = []): ElasticsearchInstanceFormValue[] => {
  const kwargsMap = new Map(kwargs.filter((item) => item.key).map((item) => [item.key, item.value]));
  const instancesValue = kwargsMap.get(ES_INSTANCES_KEY);
  const parsedInstances = parseEsInstancesValue(instancesValue);

  if (parsedInstances.length > 0) {
    return parsedInstances.map((item, index) => ({
      id: String(item.id || `es-${index + 1}`),
      name: String(item.name || `${ES_AUTO_NAME_PREFIX}${index + 1}`),
      url: String(item.url || ''),
      username: String(item.username || ''),
      password: String(item.password || ''),
      api_key: String(item.api_key || ''),
      verify_certs: parseEsBoolean(item.verify_certs),
      testStatus: 'untested',
    }));
  }

  const hasLegacyConfig = ['url', 'username', 'password', 'api_key'].some((key) => kwargsMap.has(key));
  if (hasLegacyConfig) {
    return [{
      id: 'es-1',
      name: 'Elasticsearch - 1',
      url: String(kwargsMap.get('url') || ''),
      username: String(kwargsMap.get('username') || ''),
      password: String(kwargsMap.get('password') || ''),
      api_key: String(kwargsMap.get('api_key') || ''),
      verify_certs: parseEsBoolean(kwargsMap.get('verify_certs')),
      testStatus: 'untested',
    }];
  }

  return [getDefaultEsInstance('Elasticsearch - 1')];
};

const serializeEsToolConfig = (instances: ElasticsearchInstanceFormValue[]): ToolVariable[] => {
  const normalized = instances.map((instance) => {
    const copy = { ...instance };
    delete copy.testStatus;
    return copy;
  });
  return [
    { key: ES_INSTANCES_KEY, value: JSON.stringify(normalized) },
    { key: ES_DEFAULT_INSTANCE_ID_KEY, value: normalized[0]?.id || '' },
  ];
};

const isEsTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === ES_TOOL_NAME;

// ── Jenkins ───────────────────────────────────────────────────────────────────

const JENKINS_TOOL_NAME = 'jenkins';
const JENKINS_INSTANCES_KEY = 'jenkins_instances';
const JENKINS_DEFAULT_INSTANCE_ID_KEY = 'jenkins_default_instance_id';
const JENKINS_AUTO_NAME_PREFIX = 'Jenkins - ';

const createJenkinsInstanceId = () => `jenkins-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const getDefaultJenkinsInstance = (name: string): JenkinsInstanceFormValue => ({
  id: createJenkinsInstanceId(),
  name,
  jenkins_url: '',
  jenkins_username: '',
  jenkins_password: '',
  testStatus: 'untested',
});

const getNextJenkinsInstanceName = (instances: JenkinsInstanceFormValue[]) => {
  const maxIndex = instances.reduce((max, instance) => {
    const match = instance.name.match(/^Jenkins - (\d+)$/);
    if (!match) return max;
    return Math.max(max, Number(match[1]));
  }, 0);
  return `${JENKINS_AUTO_NAME_PREFIX}${maxIndex + 1}`;
};

const parseJenkinsInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) return value as Record<string, unknown>[];
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch { return []; }
  }
  return [];
};

const parseJenkinsToolConfig = (kwargs: ToolVariable[] = []): JenkinsInstanceFormValue[] => {
  const kwargsMap = new Map(kwargs.filter((item) => item.key).map((item) => [item.key, item.value]));
  const instancesValue = kwargsMap.get(JENKINS_INSTANCES_KEY);
  const parsedInstances = parseJenkinsInstancesValue(instancesValue);

  if (parsedInstances.length > 0) {
    return parsedInstances.map((item, index) => ({
      id: String(item.id || `jenkins-${index + 1}`),
      name: String(item.name || `${JENKINS_AUTO_NAME_PREFIX}${index + 1}`),
      jenkins_url: String(item.jenkins_url || ''),
      jenkins_username: String(item.jenkins_username || ''),
      jenkins_password: String(item.jenkins_password || ''),
      testStatus: 'untested',
    }));
  }

  const hasLegacyConfig = ['jenkins_url', 'jenkins_username', 'jenkins_password'].some((key) => kwargsMap.has(key));
  if (hasLegacyConfig) {
    return [{
      id: 'jenkins-1',
      name: 'Jenkins - 1',
      jenkins_url: String(kwargsMap.get('jenkins_url') || ''),
      jenkins_username: String(kwargsMap.get('jenkins_username') || ''),
      jenkins_password: String(kwargsMap.get('jenkins_password') || ''),
      testStatus: 'untested',
    }];
  }

  return [getDefaultJenkinsInstance('Jenkins - 1')];
};

const serializeJenkinsToolConfig = (instances: JenkinsInstanceFormValue[]): ToolVariable[] => {
  const normalized = instances.map((instance) => {
    const copy = { ...instance };
    delete copy.testStatus;
    return copy;
  });
  return [
    { key: JENKINS_INSTANCES_KEY, value: JSON.stringify(normalized) },
    { key: JENKINS_DEFAULT_INSTANCE_ID_KEY, value: normalized[0]?.id || '' },
  ];
};

const isJenkinsTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === JENKINS_TOOL_NAME;

// ── Kubernetes ────────────────────────────────────────────────────────────────

const KUBERNETES_TOOL_NAME = 'kubernetes';
const KUBERNETES_INSTANCES_KEY = 'kubernetes_instances';
const KUBERNETES_DEFAULT_INSTANCE_ID_KEY = 'kubernetes_default_instance_id';
const KUBERNETES_AUTO_NAME_PREFIX = 'Kubernetes - ';

const createKubernetesInstanceId = () => `kubernetes-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const getDefaultKubernetesInstance = (name: string): KubernetesInstanceFormValue => ({
  id: createKubernetesInstanceId(),
  name,
  kubeconfig_data: '',
  testStatus: 'untested',
});

const getNextKubernetesInstanceName = (instances: KubernetesInstanceFormValue[]) => {
  const maxIndex = instances.reduce((max, instance) => {
    const match = instance.name.match(/^Kubernetes - (\d+)$/);
    if (!match) return max;
    return Math.max(max, Number(match[1]));
  }, 0);
  return `${KUBERNETES_AUTO_NAME_PREFIX}${maxIndex + 1}`;
};

const parseKubernetesInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) return value as Record<string, unknown>[];
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch { return []; }
  }
  return [];
};

const parseKubernetesToolConfig = (kwargs: ToolVariable[] = []): KubernetesInstanceFormValue[] => {
  const kwargsMap = new Map(kwargs.filter((item) => item.key).map((item) => [item.key, item.value]));
  const instancesValue = kwargsMap.get(KUBERNETES_INSTANCES_KEY);
  const parsedInstances = parseKubernetesInstancesValue(instancesValue);

  if (parsedInstances.length > 0) {
    return parsedInstances.map((item, index) => ({
      id: String(item.id || `kubernetes-${index + 1}`),
      name: String(item.name || `${KUBERNETES_AUTO_NAME_PREFIX}${index + 1}`),
      kubeconfig_data: String(item.kubeconfig_data || ''),
      testStatus: 'untested',
    }));
  }

  const hasLegacyConfig = ['kubeconfig_data'].some((key) => kwargsMap.has(key));
  if (hasLegacyConfig) {
    return [{
      id: 'kubernetes-1',
      name: 'Kubernetes - 1',
      kubeconfig_data: String(kwargsMap.get('kubeconfig_data') || ''),
      testStatus: 'untested',
    }];
  }

  return [getDefaultKubernetesInstance('Kubernetes - 1')];
};

const serializeKubernetesToolConfig = (instances: KubernetesInstanceFormValue[]): ToolVariable[] => {
  const normalized = instances.map((instance) => {
    const copy = { ...instance };
    delete copy.testStatus;
    return copy;
  });
  return [
    { key: KUBERNETES_INSTANCES_KEY, value: JSON.stringify(normalized) },
    { key: KUBERNETES_DEFAULT_INSTANCE_ID_KEY, value: normalized[0]?.id || '' },
  ];
};

const isKubernetesTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === KUBERNETES_TOOL_NAME;

interface ToolSelectorProps {
  defaultTools: SelectTool[];
  onChange: (selected: SelectTool[]) => void;
}

const ToolSelector: React.FC<ToolSelectorProps> = ({ defaultTools, onChange }) => {
  const { t } = useTranslation();
  const { fetchSkillTools, testRedisConnection, testMysqlConnection, testOracleConnection, testMssqlConnection, testPostgresConnection, testEsConnection, testJenkinsConnection, testKubernetesConnection } = useSkillApi();
  const [loading, setLoading] = useState<boolean>(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [tools, setTools] = useState<SelectTool[]>([]);
  const [selectedTools, setSelectedTools] = useState<SelectTool[]>([]);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingTool, setEditingTool] = useState<SelectTool | null>(null);
  const [redisInstances, setRedisInstances] = useState<RedisInstanceFormValue[]>([]);
  const [selectedRedisInstanceId, setSelectedRedisInstanceId] = useState<string | null>(null);
  const [testingRedisConnection, setTestingRedisConnection] = useState(false);
  const [mysqlInstances, setMysqlInstances] = useState<MysqlInstanceFormValue[]>([]);
  const [selectedMysqlInstanceId, setSelectedMysqlInstanceId] = useState<string | null>(null);
  const [testingMysqlConnection, setTestingMysqlConnection] = useState(false);
  const [oracleInstances, setOracleInstances] = useState<OracleInstanceFormValue[]>([]);
  const [selectedOracleInstanceId, setSelectedOracleInstanceId] = useState<string | null>(null);
  const [testingOracleConnection, setTestingOracleConnection] = useState(false);
  const [mssqlInstances, setMssqlInstances] = useState<MssqlInstanceFormValue[]>([]);
  const [selectedMssqlInstanceId, setSelectedMssqlInstanceId] = useState<string | null>(null);
  const [testingMssqlConnection, setTestingMssqlConnection] = useState(false);
  const [postgresInstances, setPostgresInstances] = useState<PostgresInstanceFormValue[]>([]);
  const [selectedPostgresInstanceId, setSelectedPostgresInstanceId] = useState<string | null>(null);
  const [testingPostgresConnection, setTestingPostgresConnection] = useState(false);
  const [esInstances, setEsInstances] = useState<ElasticsearchInstanceFormValue[]>([]);
  const [selectedEsInstanceId, setSelectedEsInstanceId] = useState<string | null>(null);
  const [testingEsConnection, setTestingEsConnection] = useState(false);
  const [jenkinsInstances, setJenkinsInstances] = useState<JenkinsInstanceFormValue[]>([]);
  const [selectedJenkinsInstanceId, setSelectedJenkinsInstanceId] = useState<string | null>(null);
  const [testingJenkinsConnection, setTestingJenkinsConnection] = useState(false);
  const [kubernetesInstances, setKubernetesInstances] = useState<KubernetesInstanceFormValue[]>([]);
  const [selectedKubernetesInstanceId, setSelectedKubernetesInstanceId] = useState<string | null>(null);
  const [testingKubernetesConnection, setTestingKubernetesConnection] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await fetchSkillTools();
      const defaultToolMap = new Map(defaultTools.map((tool) => [tool.id, tool]));
      const defaultRedisTool = defaultTools.find((tool) => isRedisTool(tool));
      const defaultMysqlTool = defaultTools.find((tool) => isMysqlTool(tool));
      const defaultOracleTool = defaultTools.find((tool) => isOracleTool(tool));
      const defaultMssqlTool = defaultTools.find((tool) => isMssqlTool(tool));
      const defaultPostgresTool = defaultTools.find((tool) => isPostgresTool(tool));
      const defaultEsTool = defaultTools.find((tool) => isEsTool(tool));
      const defaultJenkinsTool = defaultTools.find((tool) => isJenkinsTool(tool));
      const defaultKubernetesTool = defaultTools.find((tool) => isKubernetesTool(tool));
      const fetchedTools = data.map((tool: any) => {
        const defaultTool = defaultToolMap.get(tool.id);
        const kwargs = (tool.params.kwargs || [])
          .filter((kwarg: any) => kwarg.key)
          .map((kwarg: any) => ({
            ...kwarg,
            value: (defaultTool?.kwargs ?? []).find((dk: any) => dk.key === kwarg.key)?.value ?? kwarg.value,
          }));
        return {
          id: tool.id,
          name: tool.display_name || tool.name,
          rawName: tool.name,
          icon: tool.icon || 'gongjuji',
          description: tool.description_tr || tool.description || '',
          kwargs,
        };
      });
      setTools(fetchedTools);

      const initialSelectedTools = fetchedTools
        .filter((tool) => defaultToolMap.has(tool.id) || (isRedisTool(tool) && !!defaultRedisTool) || (isMysqlTool(tool) && !!defaultMysqlTool) || (isOracleTool(tool) && !!defaultOracleTool) || (isMssqlTool(tool) && !!defaultMssqlTool) || (isPostgresTool(tool) && !!defaultPostgresTool) || (isEsTool(tool) && !!defaultEsTool) || (isJenkinsTool(tool) && !!defaultJenkinsTool) || (isKubernetesTool(tool) && !!defaultKubernetesTool))
        .map((tool) => {
          const matchedDefaultTool = defaultToolMap.get(tool.id) || (isRedisTool(tool) ? defaultRedisTool : undefined) || (isMysqlTool(tool) ? defaultMysqlTool : undefined) || (isOracleTool(tool) ? defaultOracleTool : undefined) || (isMssqlTool(tool) ? defaultMssqlTool : undefined) || (isPostgresTool(tool) ? defaultPostgresTool : undefined) || (isEsTool(tool) ? defaultEsTool : undefined) || (isJenkinsTool(tool) ? defaultJenkinsTool : undefined) || (isKubernetesTool(tool) ? defaultKubernetesTool : undefined);
          if (!matchedDefaultTool) {
            return tool;
          }
          return {
            ...tool,
            kwargs: matchedDefaultTool.kwargs?.length ? matchedDefaultTool.kwargs : tool.kwargs,
          };
        });
      setSelectedTools(initialSelectedTools);
      onChange(initialSelectedTools);
    } catch (error) {
      console.error(t('common.fetchFailed'), error);
    } finally {
      setLoading(false);
    }
  };

  const openModal = () => {
    setModalVisible(true);
  };

  const handleModalConfirm = (selectedIds: number[]) => {
    const updatedSelectedTools = tools.filter((tool) => selectedIds.includes(tool.id));
    setSelectedTools(updatedSelectedTools);
    onChange(updatedSelectedTools);
    setModalVisible(false);
  };

  const handleModalCancel = () => {
    setModalVisible(false);
  };

  const removeSelectedTool = (toolId: number) => {
    const updatedSelectedTools = selectedTools.filter((tool) => tool.id !== toolId);
    setSelectedTools(updatedSelectedTools);
    onChange(updatedSelectedTools);
  };

  const openEditModal = (tool: SelectTool) => {
    setEditingTool(tool);
    if (isRedisTool(tool)) {
      const instances = parseRedisToolConfig(tool.kwargs);
      setRedisInstances(instances);
      setSelectedRedisInstanceId(instances[0]?.id || null);
    } else if (isMysqlTool(tool)) {
      const instances = parseMysqlToolConfig(tool.kwargs);
      setMysqlInstances(instances);
      setSelectedMysqlInstanceId(instances[0]?.id || null);
    } else if (isOracleTool(tool)) {
      const instances = parseOracleToolConfig(tool.kwargs);
      setOracleInstances(instances);
      setSelectedOracleInstanceId(instances[0]?.id || null);
    } else if (isMssqlTool(tool)) {
      const instances = parseMssqlToolConfig(tool.kwargs);
      setMssqlInstances(instances);
      setSelectedMssqlInstanceId(instances[0]?.id || null);
    } else if (isPostgresTool(tool)) {
      const instances = parsePostgresToolConfig(tool.kwargs);
      setPostgresInstances(instances);
      setSelectedPostgresInstanceId(instances[0]?.id || null);
    } else if (isEsTool(tool)) {
      const instances = parseEsToolConfig(tool.kwargs);
      setEsInstances(instances);
      setSelectedEsInstanceId(instances[0]?.id || null);
    } else if (isJenkinsTool(tool)) {
      const instances = parseJenkinsToolConfig(tool.kwargs);
      setJenkinsInstances(instances);
      setSelectedJenkinsInstanceId(instances[0]?.id || null);
    } else if (isKubernetesTool(tool)) {
      const instances = parseKubernetesToolConfig(tool.kwargs);
      setKubernetesInstances(instances);
      setSelectedKubernetesInstanceId(instances[0]?.id || null);
    } else {
      form.setFieldsValue({
        kwargs: tool.kwargs?.map((item: any) => ({ key: item.key, value: item.value, type: item.type, isRequired: item.isRequired })) || [],
      });
    }
    setEditModalVisible(true);
  };

  const handleEditModalOk = () => {
    if (isRedisTool(editingTool)) {
      const trimmedNames = redisInstances.map((instance) => instance.name.trim()).filter(Boolean);
      if (redisInstances.length === 0) {
        message.error(t('tool.redis.noInstances'));
        return;
      }
      if (trimmedNames.length !== redisInstances.length) {
        message.error(t('tool.redis.instanceNameRequired'));
        return;
      }
      if (new Set(trimmedNames).size !== trimmedNames.length) {
        message.error(t('tool.redis.duplicateInstanceName'));
        return;
      }
      if (redisInstances.some((instance) => !instance.url.trim())) {
        message.error(t('tool.redis.urlRequired'));
        return;
      }
      if (editingTool) {
        const updatedTool = {
          ...editingTool,
          kwargs: serializeRedisToolConfig(redisInstances.map((instance) => ({ ...instance, name: instance.name.trim(), url: instance.url.trim() }))),
        };
        const updatedSelectedTools = selectedTools.map((tool) => (tool.id === editingTool.id ? updatedTool : tool));
        setSelectedTools(updatedSelectedTools);
        onChange(updatedSelectedTools);
      }
      setEditModalVisible(false);
      setEditingTool(null);
      return;
    }

    if (isMysqlTool(editingTool)) {
      const trimmedNames = mysqlInstances.map((instance) => instance.name.trim()).filter(Boolean);
      if (mysqlInstances.length === 0) {
        message.error(t('tool.mysql.noInstances'));
        return;
      }
      if (trimmedNames.length !== mysqlInstances.length) {
        message.error(t('tool.mysql.instanceNameRequired'));
        return;
      }
      if (new Set(trimmedNames).size !== trimmedNames.length) {
        message.error(t('tool.mysql.duplicateInstanceName'));
        return;
      }
      if (mysqlInstances.some((instance) => !instance.host.trim())) {
        message.error(t('tool.mysql.hostRequired'));
        return;
      }
      if (editingTool) {
        const updatedTool = {
          ...editingTool,
          kwargs: serializeMysqlToolConfig(mysqlInstances.map((instance) => ({ ...instance, name: instance.name.trim(), host: instance.host.trim() }))),
        };
        const updatedSelectedTools = selectedTools.map((tool) => (tool.id === editingTool.id ? updatedTool : tool));
        setSelectedTools(updatedSelectedTools);
        onChange(updatedSelectedTools);
      }
      setEditModalVisible(false);
      setEditingTool(null);
      return;
    }

    if (isOracleTool(editingTool)) {
      const trimmedNames = oracleInstances.map((instance) => instance.name.trim()).filter(Boolean);
      if (oracleInstances.length === 0) {
        message.error(t('tool.oracle.noInstances'));
        return;
      }
      if (trimmedNames.length !== oracleInstances.length) {
        message.error(t('tool.oracle.instanceNameRequired'));
        return;
      }
      if (new Set(trimmedNames).size !== trimmedNames.length) {
        message.error(t('tool.oracle.duplicateInstanceName'));
        return;
      }
      if (oracleInstances.some((instance) => !instance.host.trim())) {
        message.error(t('tool.oracle.hostRequired'));
        return;
      }
      if (editingTool) {
        const updatedTool = {
          ...editingTool,
          kwargs: serializeOracleToolConfig(oracleInstances.map((instance) => ({ ...instance, name: instance.name.trim(), host: instance.host.trim() }))),
        };
        const updatedSelectedTools = selectedTools.map((tool) => (tool.id === editingTool.id ? updatedTool : tool));
        setSelectedTools(updatedSelectedTools);
        onChange(updatedSelectedTools);
      }
      setEditModalVisible(false);
      setEditingTool(null);
      return;
    }

    if (isMssqlTool(editingTool)) {
      const trimmedNames = mssqlInstances.map((instance) => instance.name.trim()).filter(Boolean);
      if (mssqlInstances.length === 0) {
        message.error(t('tool.mssql.noInstances'));
        return;
      }
      if (trimmedNames.length !== mssqlInstances.length) {
        message.error(t('tool.mssql.instanceNameRequired'));
        return;
      }
      if (new Set(trimmedNames).size !== trimmedNames.length) {
        message.error(t('tool.mssql.duplicateInstanceName'));
        return;
      }
      if (mssqlInstances.some((instance) => !instance.host.trim())) {
        message.error(t('tool.mssql.hostRequired'));
        return;
      }
      if (editingTool) {
        const updatedTool = {
          ...editingTool,
          kwargs: serializeMssqlToolConfig(mssqlInstances.map((instance) => ({ ...instance, name: instance.name.trim(), host: instance.host.trim() }))),
        };
        const updatedSelectedTools = selectedTools.map((tool) => (tool.id === editingTool.id ? updatedTool : tool));
        setSelectedTools(updatedSelectedTools);
        onChange(updatedSelectedTools);
      }
      setEditModalVisible(false);
      setEditingTool(null);
      return;
    }

    if (isPostgresTool(editingTool)) {
      const trimmedNames = postgresInstances.map((instance) => instance.name.trim()).filter(Boolean);
      if (postgresInstances.length === 0) {
        message.error(t('tool.postgres.noInstances'));
        return;
      }
      if (trimmedNames.length !== postgresInstances.length) {
        message.error(t('tool.postgres.instanceNameRequired'));
        return;
      }
      if (new Set(trimmedNames).size !== trimmedNames.length) {
        message.error(t('tool.postgres.duplicateInstanceName'));
        return;
      }
      if (postgresInstances.some((instance) => !instance.host.trim())) {
        message.error(t('tool.postgres.hostRequired'));
        return;
      }
      if (editingTool) {
        const updatedTool = {
          ...editingTool,
          kwargs: serializePostgresToolConfig(postgresInstances.map((instance) => ({ ...instance, name: instance.name.trim(), host: instance.host.trim() }))),
        };
        const updatedSelectedTools = selectedTools.map((tool) => (tool.id === editingTool.id ? updatedTool : tool));
        setSelectedTools(updatedSelectedTools);
        onChange(updatedSelectedTools);
      }
      setEditModalVisible(false);
      setEditingTool(null);
      return;
    }

    if (isEsTool(editingTool)) {
      const trimmedNames = esInstances.map((instance) => instance.name.trim()).filter(Boolean);
      if (esInstances.length === 0) {
        message.error(t('tool.elasticsearch.noInstances'));
        return;
      }
      if (trimmedNames.length !== esInstances.length) {
        message.error(t('tool.elasticsearch.instanceNameRequired'));
        return;
      }
      if (new Set(trimmedNames).size !== trimmedNames.length) {
        message.error(t('tool.elasticsearch.duplicateInstanceName'));
        return;
      }
      if (esInstances.some((instance) => !instance.url.trim())) {
        message.error(t('tool.elasticsearch.urlRequired'));
        return;
      }
      if (editingTool) {
        const updatedTool = {
          ...editingTool,
          kwargs: serializeEsToolConfig(esInstances.map((instance) => ({ ...instance, name: instance.name.trim(), url: instance.url.trim() }))),
        };
        const updatedSelectedTools = selectedTools.map((tool) => (tool.id === editingTool.id ? updatedTool : tool));
        setSelectedTools(updatedSelectedTools);
        onChange(updatedSelectedTools);
      }
      setEditModalVisible(false);
      setEditingTool(null);
      return;
    }

    if (isJenkinsTool(editingTool)) {
      const trimmedNames = jenkinsInstances.map((instance) => instance.name.trim()).filter(Boolean);
      if (jenkinsInstances.length === 0) {
        message.error(t('tool.jenkins.noInstances'));
        return;
      }
      if (trimmedNames.length !== jenkinsInstances.length) {
        message.error(t('tool.jenkins.instanceNameRequired'));
        return;
      }
      if (new Set(trimmedNames).size !== trimmedNames.length) {
        message.error(t('tool.jenkins.duplicateInstanceName'));
        return;
      }
      if (jenkinsInstances.some((instance) => !instance.jenkins_url.trim())) {
        message.error(t('tool.jenkins.urlRequired'));
        return;
      }
      if (editingTool) {
        const updatedTool = {
          ...editingTool,
          kwargs: serializeJenkinsToolConfig(jenkinsInstances.map((instance) => ({ ...instance, name: instance.name.trim(), jenkins_url: instance.jenkins_url.trim() }))),
        };
        const updatedSelectedTools = selectedTools.map((tool) => (tool.id === editingTool.id ? updatedTool : tool));
        setSelectedTools(updatedSelectedTools);
        onChange(updatedSelectedTools);
      }
      setEditModalVisible(false);
      setEditingTool(null);
      return;
    }

    if (isKubernetesTool(editingTool)) {
      const trimmedNames = kubernetesInstances.map((instance) => instance.name.trim()).filter(Boolean);
      if (kubernetesInstances.length === 0) {
        message.error(t('tool.kubernetes.noInstances'));
        return;
      }
      if (trimmedNames.length !== kubernetesInstances.length) {
        message.error(t('tool.kubernetes.instanceNameRequired'));
        return;
      }
      if (new Set(trimmedNames).size !== trimmedNames.length) {
        message.error(t('tool.kubernetes.duplicateInstanceName'));
        return;
      }
      if (editingTool) {
        const updatedTool = {
          ...editingTool,
          kwargs: serializeKubernetesToolConfig(kubernetesInstances.map((instance) => ({ ...instance, name: instance.name.trim() }))),
        };
        const updatedSelectedTools = selectedTools.map((tool) => (tool.id === editingTool.id ? updatedTool : tool));
        setSelectedTools(updatedSelectedTools);
        onChange(updatedSelectedTools);
      }
      setEditModalVisible(false);
      setEditingTool(null);
      return;
    }

    form.validateFields().then((values) => {
      if (editingTool) {
        const updatedTool = {
          ...editingTool,
          kwargs: values.kwargs,
        };
        const updatedSelectedTools = selectedTools.map((tool) => (tool.id === editingTool.id ? updatedTool : tool));
        setSelectedTools(updatedSelectedTools);
        onChange(updatedSelectedTools);
      }
      setEditModalVisible(false);
      setEditingTool(null);
    });
  };

  const handleEditModalCancel = () => {
    setEditModalVisible(false);
    setEditingTool(null);
    setRedisInstances([]);
    setSelectedRedisInstanceId(null);
    setMysqlInstances([]);
    setSelectedMysqlInstanceId(null);
    setOracleInstances([]);
    setSelectedOracleInstanceId(null);
    setMssqlInstances([]);
    setSelectedMssqlInstanceId(null);
    setPostgresInstances([]);
    setSelectedPostgresInstanceId(null);
    setEsInstances([]);
    setSelectedEsInstanceId(null);
    setJenkinsInstances([]);
    setSelectedJenkinsInstanceId(null);
    setKubernetesInstances([]);
    setSelectedKubernetesInstanceId(null);
  };

  const handleAddRedisInstance = () => {
    const nextInstance = getDefaultRedisInstance(getNextRedisInstanceName(redisInstances));
    setRedisInstances((prev) => [...prev, nextInstance]);
    setSelectedRedisInstanceId(nextInstance.id);
  };

  const handleDeleteRedisInstance = (instanceId: string) => {
    setRedisInstances((prev) => {
      const nextInstances = prev.filter((instance) => instance.id !== instanceId);
      if (selectedRedisInstanceId === instanceId) {
        setSelectedRedisInstanceId(nextInstances[0]?.id || null);
      }
      return nextInstances;
    });
  };

  const handleRedisInstanceChange = <K extends keyof RedisInstanceFormValue>(
    instanceId: string,
    field: K,
    value: RedisInstanceFormValue[K],
  ) => {
    setRedisInstances((prev) => prev.map((instance) => (
      instance.id === instanceId ? { ...instance, [field]: value, testStatus: 'untested' } : instance
    )));
  };

  const handleTestRedisInstance = async () => {
    const currentInstance = redisInstances.find((instance) => instance.id === selectedRedisInstanceId);
    if (!currentInstance) {
      return;
    }
    setTestingRedisConnection(true);
    try {
      const payload = { ...currentInstance };
      delete payload.testStatus;
      await testRedisConnection(payload);
      message.success(t('tool.redis.status.success'));
      setRedisInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'success' } : instance
      )));
    } catch {
      setRedisInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'failed' } : instance
      )));
    } finally {
      setTestingRedisConnection(false);
    }
  };

  const handleAddMysqlInstance = () => {
    const nextInstance = getDefaultMysqlInstance(getNextMysqlInstanceName(mysqlInstances));
    setMysqlInstances((prev) => [...prev, nextInstance]);
    setSelectedMysqlInstanceId(nextInstance.id);
  };

  const handleDeleteMysqlInstance = (instanceId: string) => {
    setMysqlInstances((prev) => {
      const nextInstances = prev.filter((instance) => instance.id !== instanceId);
      if (selectedMysqlInstanceId === instanceId) {
        setSelectedMysqlInstanceId(nextInstances[0]?.id || null);
      }
      return nextInstances;
    });
  };

  const handleMysqlInstanceChange = <K extends keyof MysqlInstanceFormValue>(
    instanceId: string,
    field: K,
    value: MysqlInstanceFormValue[K],
  ) => {
    setMysqlInstances((prev) => prev.map((instance) => (
      instance.id === instanceId ? { ...instance, [field]: value, testStatus: 'untested' } : instance
    )));
  };

  const handleTestMysqlInstance = async () => {
    const currentInstance = mysqlInstances.find((instance) => instance.id === selectedMysqlInstanceId);
    if (!currentInstance) {
      return;
    }
    setTestingMysqlConnection(true);
    try {
      const payload = { ...currentInstance };
      delete payload.testStatus;
      await testMysqlConnection(payload);
      message.success(t('tool.mysql.status.success'));
      setMysqlInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'success' } : instance
      )));
    } catch {
      setMysqlInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'failed' } : instance
      )));
    } finally {
      setTestingMysqlConnection(false);
    }
  };

  const handleAddOracleInstance = () => {
    const nextInstance = getDefaultOracleInstance(getNextOracleInstanceName(oracleInstances));
    setOracleInstances((prev) => [...prev, nextInstance]);
    setSelectedOracleInstanceId(nextInstance.id);
  };

  const handleDeleteOracleInstance = (instanceId: string) => {
    setOracleInstances((prev) => {
      const nextInstances = prev.filter((instance) => instance.id !== instanceId);
      if (selectedOracleInstanceId === instanceId) {
        setSelectedOracleInstanceId(nextInstances[0]?.id || null);
      }
      return nextInstances;
    });
  };

  const handleOracleInstanceChange = <K extends keyof OracleInstanceFormValue>(
    instanceId: string,
    field: K,
    value: OracleInstanceFormValue[K],
  ) => {
    setOracleInstances((prev) => prev.map((instance) => (
      instance.id === instanceId ? { ...instance, [field]: value, testStatus: 'untested' } : instance
    )));
  };

  const handleTestOracleInstance = async () => {
    const currentInstance = oracleInstances.find((instance) => instance.id === selectedOracleInstanceId);
    if (!currentInstance) {
      return;
    }
    setTestingOracleConnection(true);
    try {
      const payload = { ...currentInstance };
      delete payload.testStatus;
      await testOracleConnection(payload);
      message.success(t('tool.oracle.status.success'));
      setOracleInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'success' } : instance
      )));
    } catch {
      setOracleInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'failed' } : instance
      )));
    } finally {
      setTestingOracleConnection(false);
    }
  };

  const handleAddMssqlInstance = () => {
    const nextInstance = getDefaultMssqlInstance(getNextMssqlInstanceName(mssqlInstances));
    setMssqlInstances((prev) => [...prev, nextInstance]);
    setSelectedMssqlInstanceId(nextInstance.id);
  };

  const handleDeleteMssqlInstance = (instanceId: string) => {
    setMssqlInstances((prev) => {
      const nextInstances = prev.filter((instance) => instance.id !== instanceId);
      if (selectedMssqlInstanceId === instanceId) {
        setSelectedMssqlInstanceId(nextInstances[0]?.id || null);
      }
      return nextInstances;
    });
  };

  const handleMssqlInstanceChange = <K extends keyof MssqlInstanceFormValue>(
    instanceId: string,
    field: K,
    value: MssqlInstanceFormValue[K],
  ) => {
    setMssqlInstances((prev) => prev.map((instance) => (
      instance.id === instanceId ? { ...instance, [field]: value, testStatus: 'untested' } : instance
    )));
  };

  const handleTestMssqlInstance = async () => {
    const currentInstance = mssqlInstances.find((instance) => instance.id === selectedMssqlInstanceId);
    if (!currentInstance) {
      return;
    }
    setTestingMssqlConnection(true);
    try {
      const payload = { ...currentInstance };
      delete payload.testStatus;
      await testMssqlConnection(payload);
      message.success(t('tool.mssql.status.success'));
      setMssqlInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'success' } : instance
      )));
    } catch {
      setMssqlInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'failed' } : instance
      )));
    } finally {
      setTestingMssqlConnection(false);
    }
  };

  const handleAddPostgresInstance = () => {
    const nextInstance = getDefaultPostgresInstance(getNextPostgresInstanceName(postgresInstances));
    setPostgresInstances((prev) => [...prev, nextInstance]);
    setSelectedPostgresInstanceId(nextInstance.id);
  };

  const handleDeletePostgresInstance = (instanceId: string) => {
    setPostgresInstances((prev) => {
      const nextInstances = prev.filter((instance) => instance.id !== instanceId);
      if (selectedPostgresInstanceId === instanceId) {
        setSelectedPostgresInstanceId(nextInstances[0]?.id || null);
      }
      return nextInstances;
    });
  };

  const handlePostgresInstanceChange = <K extends keyof PostgresInstanceFormValue>(
    instanceId: string,
    field: K,
    value: PostgresInstanceFormValue[K],
  ) => {
    setPostgresInstances((prev) => prev.map((instance) => (
      instance.id === instanceId ? { ...instance, [field]: value, testStatus: 'untested' } : instance
    )));
  };

  const handleTestPostgresInstance = async () => {
    const currentInstance = postgresInstances.find((instance) => instance.id === selectedPostgresInstanceId);
    if (!currentInstance) return;
    setTestingPostgresConnection(true);
    try {
      const payload = { ...currentInstance };
      delete payload.testStatus;
      await testPostgresConnection(payload);
      message.success(t('tool.postgres.status.success'));
      setPostgresInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'success' } : instance
      )));
    } catch {
      setPostgresInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'failed' } : instance
      )));
    } finally {
      setTestingPostgresConnection(false);
    }
  };

  const handleAddEsInstance = () => {
    const nextInstance = getDefaultEsInstance(getNextEsInstanceName(esInstances));
    setEsInstances((prev) => [...prev, nextInstance]);
    setSelectedEsInstanceId(nextInstance.id);
  };

  const handleDeleteEsInstance = (instanceId: string) => {
    setEsInstances((prev) => {
      const nextInstances = prev.filter((instance) => instance.id !== instanceId);
      if (selectedEsInstanceId === instanceId) {
        setSelectedEsInstanceId(nextInstances[0]?.id || null);
      }
      return nextInstances;
    });
  };

  const handleEsInstanceChange = <K extends keyof ElasticsearchInstanceFormValue>(
    instanceId: string,
    field: K,
    value: ElasticsearchInstanceFormValue[K],
  ) => {
    setEsInstances((prev) => prev.map((instance) => (
      instance.id === instanceId ? { ...instance, [field]: value, testStatus: 'untested' } : instance
    )));
  };

  const handleTestEsInstance = async () => {
    const currentInstance = esInstances.find((instance) => instance.id === selectedEsInstanceId);
    if (!currentInstance) return;
    setTestingEsConnection(true);
    try {
      const payload = { ...currentInstance };
      delete payload.testStatus;
      await testEsConnection(payload);
      message.success(t('tool.elasticsearch.status.success'));
      setEsInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'success' } : instance
      )));
    } catch {
      setEsInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'failed' } : instance
      )));
    } finally {
      setTestingEsConnection(false);
    }
  };

  const handleAddJenkinsInstance = () => {
    const nextInstance = getDefaultJenkinsInstance(getNextJenkinsInstanceName(jenkinsInstances));
    setJenkinsInstances((prev) => [...prev, nextInstance]);
    setSelectedJenkinsInstanceId(nextInstance.id);
  };

  const handleDeleteJenkinsInstance = (instanceId: string) => {
    setJenkinsInstances((prev) => {
      const nextInstances = prev.filter((instance) => instance.id !== instanceId);
      if (selectedJenkinsInstanceId === instanceId) {
        setSelectedJenkinsInstanceId(nextInstances[0]?.id || null);
      }
      return nextInstances;
    });
  };

  const handleJenkinsInstanceChange = <K extends keyof JenkinsInstanceFormValue>(
    instanceId: string,
    field: K,
    value: JenkinsInstanceFormValue[K],
  ) => {
    setJenkinsInstances((prev) => prev.map((instance) => (
      instance.id === instanceId ? { ...instance, [field]: value, testStatus: 'untested' } : instance
    )));
  };

  const handleTestJenkinsInstance = async () => {
    const currentInstance = jenkinsInstances.find((instance) => instance.id === selectedJenkinsInstanceId);
    if (!currentInstance) return;
    setTestingJenkinsConnection(true);
    try {
      const payload = { ...currentInstance };
      delete payload.testStatus;
      await testJenkinsConnection(payload);
      message.success(t('tool.jenkins.status.success'));
      setJenkinsInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'success' } : instance
      )));
    } catch {
      setJenkinsInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'failed' } : instance
      )));
    } finally {
      setTestingJenkinsConnection(false);
    }
  };

  const handleAddKubernetesInstance = () => {
    const nextInstance = getDefaultKubernetesInstance(getNextKubernetesInstanceName(kubernetesInstances));
    setKubernetesInstances((prev) => [...prev, nextInstance]);
    setSelectedKubernetesInstanceId(nextInstance.id);
  };

  const handleDeleteKubernetesInstance = (instanceId: string) => {
    setKubernetesInstances((prev) => {
      const nextInstances = prev.filter((instance) => instance.id !== instanceId);
      if (selectedKubernetesInstanceId === instanceId) {
        setSelectedKubernetesInstanceId(nextInstances[0]?.id || null);
      }
      return nextInstances;
    });
  };

  const handleKubernetesInstanceChange = <K extends keyof KubernetesInstanceFormValue>(
    instanceId: string,
    field: K,
    value: KubernetesInstanceFormValue[K],
  ) => {
    setKubernetesInstances((prev) => prev.map((instance) => (
      instance.id === instanceId ? { ...instance, [field]: value, testStatus: 'untested' } : instance
    )));
  };

  const handleTestKubernetesInstance = async () => {
    const currentInstance = kubernetesInstances.find((instance) => instance.id === selectedKubernetesInstanceId);
    if (!currentInstance) return;
    setTestingKubernetesConnection(true);
    try {
      const payload = { ...currentInstance };
      delete payload.testStatus;
      await testKubernetesConnection(payload);
      message.success(t('tool.kubernetes.status.success'));
      setKubernetesInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'success' } : instance
      )));
    } catch {
      setKubernetesInstances((prev) => prev.map((instance) => (
        instance.id === currentInstance.id ? { ...instance, testStatus: 'failed' } : instance
      )));
    } finally {
      setTestingKubernetesConnection(false);
    }
  };

  return (
    <div>
      <Button onClick={openModal}>+ {t('common.add')}</Button>
      <div className="grid grid-cols-2 gap-4 mt-2 pb-2">
        {selectedTools.map((tool) => (
          <div key={tool.id} className={`w-full rounded-md px-4 py-2 flex items-center justify-between ${styles.borderContainer}`}>
            <Tooltip title={tool.name}>
              <div className='flex items-center'>
                <Icon className='text-xl mr-1' type={tool.icon} />
                <span className="inline-block text-ellipsis overflow-hidden whitespace-nowrap">{tool.name}</span>
              </div>
            </Tooltip>
            <div className="flex items-center space-x-2 text-[var(--color-text-3)]">
              <EditOutlined
                className="hover:text-[var(--color-primary)] transition-colors duration-200"
                onClick={() => openEditModal(tool)}
              />
              <DeleteOutlined
                className="hover:text-[var(--color-primary)] transition-colors duration-200"
                onClick={() => removeSelectedTool(tool.id)}
              />
            </div>
          </div>
        ))}
      </div>

      <SelectorOperateModal
        title={t('skill.selecteTool')}
        visible={modalVisible}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        loading={loading}
        options={tools}
        isNeedGuide={false}
        showToolDetail={true}
        selectedOptions={selectedTools.map((tool) => tool.id)}
        onOk={handleModalConfirm}
        onCancel={handleModalCancel}
      />

      <OperateModal
        title={t('common.edit')}
        visible={editModalVisible}
        onOk={handleEditModalOk}
        onCancel={handleEditModalCancel}
        okText={t('common.save')}
        cancelText={t('common.cancel')}
        width={isRedisTool(editingTool) || isMysqlTool(editingTool) || isOracleTool(editingTool) || isMssqlTool(editingTool) || isPostgresTool(editingTool) || isEsTool(editingTool) || isJenkinsTool(editingTool) || isKubernetesTool(editingTool) ? 800 : undefined}
      >
        <Form form={form} layout="vertical">
          {isRedisTool(editingTool) ? (
            <RedisToolEditor
              instances={redisInstances}
              selectedInstanceId={selectedRedisInstanceId}
              testing={testingRedisConnection}
              onSelect={setSelectedRedisInstanceId}
              onAdd={handleAddRedisInstance}
              onDelete={handleDeleteRedisInstance}
              onChange={handleRedisInstanceChange}
              onTest={handleTestRedisInstance}
            />
          ) : isMysqlTool(editingTool) ? (
            <MysqlToolEditor
              instances={mysqlInstances}
              selectedInstanceId={selectedMysqlInstanceId}
              testing={testingMysqlConnection}
              onSelect={setSelectedMysqlInstanceId}
              onAdd={handleAddMysqlInstance}
              onDelete={handleDeleteMysqlInstance}
              onChange={handleMysqlInstanceChange}
              onTest={handleTestMysqlInstance}
            />
          ) : isOracleTool(editingTool) ? (
            <OracleToolEditor
              instances={oracleInstances}
              selectedInstanceId={selectedOracleInstanceId}
              testing={testingOracleConnection}
              onSelect={setSelectedOracleInstanceId}
              onAdd={handleAddOracleInstance}
              onDelete={handleDeleteOracleInstance}
              onChange={handleOracleInstanceChange}
              onTest={handleTestOracleInstance}
            />
          ) : isMssqlTool(editingTool) ? (
            <MssqlToolEditor
              instances={mssqlInstances}
              selectedInstanceId={selectedMssqlInstanceId}
              testing={testingMssqlConnection}
              onSelect={setSelectedMssqlInstanceId}
              onAdd={handleAddMssqlInstance}
              onDelete={handleDeleteMssqlInstance}
              onChange={handleMssqlInstanceChange}
              onTest={handleTestMssqlInstance}
            />
          ) : isPostgresTool(editingTool) ? (
            <PostgresToolEditor
              instances={postgresInstances}
              selectedInstanceId={selectedPostgresInstanceId}
              testing={testingPostgresConnection}
              onSelect={setSelectedPostgresInstanceId}
              onAdd={handleAddPostgresInstance}
              onDelete={handleDeletePostgresInstance}
              onChange={handlePostgresInstanceChange}
              onTest={handleTestPostgresInstance}
            />
          ) : isEsTool(editingTool) ? (
            <ElasticsearchToolEditor
              instances={esInstances}
              selectedInstanceId={selectedEsInstanceId}
              testing={testingEsConnection}
              onSelect={setSelectedEsInstanceId}
              onAdd={handleAddEsInstance}
              onDelete={handleDeleteEsInstance}
              onChange={handleEsInstanceChange}
              onTest={handleTestEsInstance}
            />
          ) : isJenkinsTool(editingTool) ? (
            <JenkinsToolEditor
              instances={jenkinsInstances}
              selectedInstanceId={selectedJenkinsInstanceId}
              testing={testingJenkinsConnection}
              onSelect={setSelectedJenkinsInstanceId}
              onAdd={handleAddJenkinsInstance}
              onDelete={handleDeleteJenkinsInstance}
              onChange={handleJenkinsInstanceChange}
              onTest={handleTestJenkinsInstance}
            />
          ) : isKubernetesTool(editingTool) ? (
            <KubernetesToolEditor
              instances={kubernetesInstances}
              selectedInstanceId={selectedKubernetesInstanceId}
              testing={testingKubernetesConnection}
              onSelect={setSelectedKubernetesInstanceId}
              onAdd={handleAddKubernetesInstance}
              onDelete={handleDeleteKubernetesInstance}
              onChange={handleKubernetesInstanceChange}
              onTest={handleTestKubernetesInstance}
            />
          ) : (
            <Form.List name="kwargs">
              {(fields) => (
                <>
                  {fields.length === 0 && (
                    <Empty description={t('common.noData')} />
                  )}
                  {fields.map(({ key, name, fieldKey, ...restField }) => {
                    const fieldType = form.getFieldValue(['kwargs', name, 'type']);
                    const fieldLabel = form.getFieldValue(['kwargs', name, 'key']);
                    const isRequired = form.getFieldValue(['kwargs', name, 'isRequired']);

                    const renderInput = () => {
                      if (isMonitorTool(editingTool) && fieldLabel === 'team_id') {
                        return (
                          <GroupTreeSelect
                            multiple={false}
                            showSearch
                            placeholder={t('common.pleaseSelect')}
                          />
                        );
                      }

                      switch (fieldType) {
                        case 'text':
                          return <Input />;
                        case 'textarea':
                          return <TextArea rows={4} />;
                        case 'password':
                          return <EditablePasswordField />;
                        case 'number':
                          return <InputNumber style={{ width: '100%' }} />;
                        case 'checkbox':
                          return <Switch />;
                        default:
                          return <Input />;
                      }
                    };

                    return (
                      <Form.Item
                        key={key}
                        {...restField}
                        name={[name, 'value']}
                        fieldKey={[fieldKey ?? '', 'value']}
                        label={fieldLabel}
                        rules={[{ required: isRequired, message: `${t('common.inputMsg')}${fieldLabel}` }]}
                        valuePropName={fieldType === 'checkbox' ? 'checked' : 'value'}
                      >
                        {renderInput()}
                      </Form.Item>
                    );
                  })}
                </>
              )}
            </Form.List>
          )}
        </Form>
      </OperateModal>
    </div>
  );
};

export default ToolSelector;
