import { describe, expect, it } from 'vitest';
import { resolveTopologyObjectIcon, topologyObjectIconSrc } from '../topology-object-icon';

describe('APM 拓扑对象图标', () => {
  it('按推断系统给出对象库里的对应图标', () => {
    expect(resolveTopologyObjectIcon('redis')).toEqual({ file: 'cc-redis_REDIS', kind: 'redis' });
    expect(resolveTopologyObjectIcon('postgresql')).toEqual({ file: 'cc-postgresql_PostgreSQL', kind: 'postgresql' });
    expect(resolveTopologyObjectIcon('postgres')).toEqual({ file: 'cc-postgresql_PostgreSQL', kind: 'postgresql' });
    expect(resolveTopologyObjectIcon('mysql')).toEqual({ file: 'cc-mysql_MySQL', kind: 'mysql' });
    expect(topologyObjectIconSrc('redis')).toBe('/assets/icons/cc-redis_REDIS.svg');
  });

  it('服务名带 gateway 时识别为网关图标', () => {
    expect(resolveTopologyObjectIcon('http', 'demo-payment-gateway')).toEqual({
      file: 'cc-nginx_Nginx',
      kind: 'gateway',
    });
    expect(resolveTopologyObjectIcon('demo-payment-gateway', 'demo-payment-gateway').kind).toBe('gateway');
  });

  it('无法识别时回退默认对象图标', () => {
    expect(resolveTopologyObjectIcon('http', 'orders-upstream')).toEqual({
      file: 'cc-default_默认',
      kind: 'default',
    });
    expect(resolveTopologyObjectIcon('', 'some-internal-api')).toEqual({
      file: 'cc-default_默认',
      kind: 'default',
    });
  });

  it('常用中间件也能命中对象库图标', () => {
    expect(resolveTopologyObjectIcon('kafka').kind).toBe('kafka');
    expect(resolveTopologyObjectIcon('consul').file).toBe('cc-consul_Consul');
    expect(resolveTopologyObjectIcon('zookeeper').file).toBe('cc-zookeeper_ZooKeeper');
    expect(resolveTopologyObjectIcon('influxdb').file).toBe('cc-influxdb_InfluxDB');
    expect(resolveTopologyObjectIcon('minio').file).toBe('cc-minio_Minio');
  });
});
