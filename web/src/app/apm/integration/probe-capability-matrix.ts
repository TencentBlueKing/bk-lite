import type { ApmIngestSnippetInput } from '@/app/apm/types';

export type ProbeLanguage = ApmIngestSnippetInput['language'];

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
    frameworks: ['Express', 'NestJS', 'Koa', 'Fastify', 'HTTP'],
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
    inferredComponents: ['MySQL', 'PostgreSQL', 'Redis', 'Kafka'],
    manualInstrumentation: true,
  },
  dotnet: {
    version: '1.16.0 Linux x86_64 glibc',
    frameworks: ['ASP.NET Core', 'ASP.NET', 'gRPC'],
    inferredComponents: ['MySQL', 'PostgreSQL', 'SQL Server', 'Redis', 'MongoDB', 'Kafka', 'RabbitMQ'],
    manualInstrumentation: false,
  },
};

export function getProbeCapability(language: ProbeLanguage): ProbeCapability {
  return PROBE_CAPABILITY_MATRIX[language];
}
