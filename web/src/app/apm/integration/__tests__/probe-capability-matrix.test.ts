import { describe, expect, it } from 'vitest';

import { getProbeCapability, PROBE_CAPABILITY_MATRIX } from '../probe-capability-matrix';

describe('APM 探针能力矩阵', () => {
  it('按钉死探针版本维护精选 Web/RPC 框架', () => {
    expect(PROBE_CAPABILITY_MATRIX.java.version).toBe('2.31.1');
    expect(PROBE_CAPABILITY_MATRIX.nodejs.version).toBe('0.79.0');
    expect(PROBE_CAPABILITY_MATRIX.python.version).toBe('0.65b0 / SDK 1.44.0');
    expect(PROBE_CAPABILITY_MATRIX.go.version).toBe('v1.46.0');
    expect(PROBE_CAPABILITY_MATRIX.dotnet.version).toBe('1.16.0 Linux x86_64 glibc');

    expect(PROBE_CAPABILITY_MATRIX.java.frameworks).toEqual(expect.arrayContaining(['Spring MVC', 'Dubbo', 'gRPC']));
    expect(PROBE_CAPABILITY_MATRIX.nodejs.frameworks).toEqual(expect.arrayContaining(['Express', 'NestJS', 'Koa', 'HTTP']));
    expect(PROBE_CAPABILITY_MATRIX.nodejs.frameworks).not.toContain('Fastify');
    expect(PROBE_CAPABILITY_MATRIX.go.inferredComponents).toEqual([]);
    expect(PROBE_CAPABILITY_MATRIX.php.frameworks).toEqual(expect.arrayContaining(['Laravel', 'Symfony', 'Slim', 'Guzzle']));
    expect(PROBE_CAPABILITY_MATRIX.obi.frameworks).toEqual(['Go net/http']);
    expect(PROBE_CAPABILITY_MATRIX.python.frameworks).toEqual(expect.arrayContaining(['Django', 'Flask', 'FastAPI']));
    expect(PROBE_CAPABILITY_MATRIX.go.manualInstrumentation).toBe(true);
    expect(PROBE_CAPABILITY_MATRIX.ruby.version).toBe('SDK 1.13.1');
    expect(PROBE_CAPABILITY_MATRIX.ruby.frameworks).toEqual(['Rack']);
    expect(PROBE_CAPABILITY_MATRIX.cpp.version).toBe('v1.30.0');
    expect(PROBE_CAPABILITY_MATRIX.cpp.frameworks).toEqual(['entry-span']);
    expect(PROBE_CAPABILITY_MATRIX.erlang.frameworks).toEqual(['entry-span']);
    expect(PROBE_CAPABILITY_MATRIX.swift.frameworks).toEqual(['entry-span']);
    expect(PROBE_CAPABILITY_MATRIX.cpp.manualInstrumentation).toBe(false);
    expect(PROBE_CAPABILITY_MATRIX.erlang.version).toBe('SDK 1.7.0');
    expect(PROBE_CAPABILITY_MATRIX.swift.version).toBe('2.6.0');
    expect(PROBE_CAPABILITY_MATRIX.cpp.inferredComponents).toEqual([]);
    expect(PROBE_CAPABILITY_MATRIX.erlang.inferredComponents).toEqual([]);
    expect(PROBE_CAPABILITY_MATRIX.swift.inferredComponents).toEqual([]);
    expect(getProbeCapability('dotnet').frameworks).not.toContain('ASP.NET');
    expect(getProbeCapability('dotnet', 'windows').frameworks).toEqual(
      expect.arrayContaining(['ASP.NET Core', 'ASP.NET Framework', 'gRPC']),
    );
    expect(getProbeCapability('dotnet', 'windows').inferredComponents).toEqual([]);
    expect(PROBE_CAPABILITY_MATRIX.java.manualInstrumentation).toBe(false);
  });

  it('发现能力只列出可打出 Client Span 的推断组件类型', () => {
    expect(PROBE_CAPABILITY_MATRIX.java.inferredComponents).toEqual(
      expect.arrayContaining(['MySQL', 'Redis', 'Kafka']),
    );
    expect(PROBE_CAPABILITY_MATRIX.nodejs.inferredComponents).toEqual(
      expect.arrayContaining(['MySQL', 'Redis', 'Kafka']),
    );
    for (const capability of Object.values(PROBE_CAPABILITY_MATRIX)) {
      expect(capability.inferredComponents.join(' ')).not.toMatch(/CMDB|服务目录|应用列表/);
    }
  });
});
