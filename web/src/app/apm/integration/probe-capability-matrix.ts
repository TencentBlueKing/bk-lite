import type { ApmIngestSnippetInput } from '@/app/apm/types';

export type ProbeLanguage = ApmIngestSnippetInput['language'];

export type ProbePlatform = 'linux' | 'windows';

export interface ProbeCapability {
  version: string;
  frameworks: readonly string[];
  inferredComponents: readonly string[];
  manualInstrumentation: boolean;
}

export const PROBE_CAPABILITY_MATRIX: Record<ProbeLanguage, ProbeCapability> = {
  java: {
    version: '2.31.1',
    frameworks: ['Spring MVC', 'Spring WebFlux', 'Servlet', 'Dubbo', 'gRPC', 'JAX-RS'],
    inferredComponents: ['MySQL', 'PostgreSQL', 'Redis', 'MongoDB', 'Kafka', 'RabbitMQ', 'Elasticsearch'],
    manualInstrumentation: false,
  },
  nodejs: {
    version: '0.79.0',
    frameworks: ['Express', 'NestJS', 'Koa', 'HTTP'],
    inferredComponents: ['MySQL', 'PostgreSQL', 'Redis', 'MongoDB', 'Kafka'],
    manualInstrumentation: false,
  },
  python: {
    version: '0.65b0 / SDK 1.44.0',
    frameworks: ['Django', 'Flask', 'FastAPI', 'Starlette', 'Tornado'],
    inferredComponents: ['MySQL', 'PostgreSQL', 'Redis', 'MongoDB', 'Kafka', 'RabbitMQ'],
    manualInstrumentation: false,
  },
  go: {
    version: 'v1.46.0',
    frameworks: ['net/http', 'gRPC', 'Gin', 'Echo'],
    inferredComponents: [],
    manualInstrumentation: true,
  },
  dotnet: {
    version: '1.16.0 Linux x86_64 glibc',
    frameworks: ['ASP.NET Core', 'gRPC'],
    inferredComponents: ['MySQL', 'PostgreSQL', 'SQL Server', 'Redis', 'MongoDB', 'Kafka', 'RabbitMQ'],
    manualInstrumentation: false,
  },
  php: {
    version: '1.4.2 / PHP NTS 8.1–8.5',
    frameworks: ['Laravel（PHP 8.2+）', 'Symfony', 'Slim', 'Guzzle'],
    inferredComponents: ['PDO（PHP 8.2+）', 'MySQLi（PHP 8.2+）'],
    manualInstrumentation: false,
  },
  obi: {
    version: 'OBI v1.0.0',
    frameworks: ['Go net/http'],
    inferredComponents: [],
    manualInstrumentation: false,
  },
  ruby: {
    version: 'SDK 1.13.1',
    frameworks: ['Rack'],
    inferredComponents: [],
    manualInstrumentation: true,
  },
  cpp: {
    version: 'v1.30.0',
    frameworks: ['entry-span'],
    inferredComponents: [],
    manualInstrumentation: false,
  },
  erlang: {
    version: 'SDK 1.7.0',
    frameworks: ['entry-span'],
    inferredComponents: [],
    manualInstrumentation: false,
  },
  swift: {
    version: '2.6.0',
    frameworks: ['entry-span'],
    inferredComponents: [],
    manualInstrumentation: false,
  },
  collector: {
    version: 'OTLP/HTTP',
    frameworks: ['OTLP Trace'],
    inferredComponents: [],
    manualInstrumentation: false,
  },
};

const DOTNET_WINDOWS_CAPABILITY: ProbeCapability = {
  version: '1.16.0 Windows x64',
  frameworks: ['ASP.NET Core', 'ASP.NET Framework', 'gRPC'],
  inferredComponents: [],
  manualInstrumentation: false,
};

export function getProbeCapability(language: ProbeLanguage, platform: ProbePlatform = 'linux'): ProbeCapability {
  if (language === 'dotnet' && platform === 'windows') return DOTNET_WINDOWS_CAPABILITY;
  return PROBE_CAPABILITY_MATRIX[language];
}
