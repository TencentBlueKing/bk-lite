import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const helperPath = path.join(
  process.cwd(),
  'src/app/opspilot/components/custom-chat-sse/liveYamlRequest.ts'
);

assert.ok(
  existsSync(helperPath),
  'DiffReportCard should have a testable live YAML request contract'
);

async function main() {
  const { buildLiveYamlRequest } = await import(pathToFileURL(helperPath).href);

  const report = {
    report_id: 'report-1',
    title: 'Kubernetes Config Fix Preview',
    cluster_name: 'prod-cluster',
    skill_id: 42,
    received_at: Date.now(),
    items: [],
  };
  const item = {
    workload_name: 'nginx-web Deployment',
    workload_type: 'Deployment',
    namespace: 'production',
    severity: 'high' as const,
    summary: 'Add resource limits',
    before_yaml: 'resources: {}',
    after_yaml: 'resources:\n  limits: {}',
  };

  assert.deepEqual(
    buildLiveYamlRequest(report, item),
    {
      kind: 'request',
      endpoint: '/opspilot/model_provider_mgmt/llm/fetch_k8s_deployment_yaml/',
      payload: {
        namespace: 'production',
        name: 'nginx-web',
        cluster_name: 'prod-cluster',
        skill_id: 42,
      },
    },
    'the current report-level skill_id contract should keep the concrete-namespace request compatible'
  );

  const legacyRequest = buildLiveYamlRequest(
    { ...report, skill_id: undefined },
    { ...item, skill_id: 7 }
  );
  assert.equal(legacyRequest?.kind, 'request');
  assert.equal(
    legacyRequest?.kind === 'request' ? legacyRequest.payload.skill_id : undefined,
    7,
    'legacy item-level skill_id reports should remain supported'
  );

  const currentRequest = buildLiveYamlRequest(report, { ...item, skill_id: 7 });
  assert.equal(
    currentRequest?.kind === 'request' ? currentRequest.payload.skill_id : undefined,
    42,
    'the current report-level contract should take precedence over the legacy item-level value'
  );

  const allNamespaces = buildLiveYamlRequest(report, { ...item, namespace: 'all' });
  assert.equal(allNamespaces?.kind, 'unavailable');
  assert.match(
    allNamespaces?.kind === 'unavailable' ? allNamespaces.message : '',
    /全部命名空间/,
    'all must explain why a namespaced deployment cannot be fetched instead of sending an empty namespace'
  );

  assert.equal(
    buildLiveYamlRequest({ ...report, skill_id: undefined }, item),
    null,
    'reports without either skill_id contract should keep the existing no-preview behavior'
  );

  const componentSource = readFileSync(
    path.join(
      process.cwd(),
      'src/app/opspilot/components/custom-chat-sse/DiffReportCard.tsx'
    ),
    'utf8'
  );

  assert.match(componentSource, /useApiClient\(\)/, 'live YAML should use the shared authenticated request client');
  assert.doesNotMatch(componentSource, /localStorage\.getItem\(['"]access_token['"]\)/);
  assert.doesNotMatch(componentSource, /startsWith\(['"]access_token=['"]\)/);
  assert.doesNotMatch(componentSource, /namespace:\s*selectedItem\.namespace\s*===\s*['"]all['"]\s*\?\s*['"]['"]/);
  assert.match(componentSource, /let cancelled = false/, 'stale responses should not overwrite a newly selected report item');

  for (const typePath of [
    'src/app/opspilot/types/global.ts',
    'src/app/opspilot/types/chat.ts',
  ]) {
    const typeSource = readFileSync(path.join(process.cwd(), typePath), 'utf8');
    assert.match(
      typeSource,
      /skill_id\?:\s*number/,
      `${typePath} should describe the report-level skill_id emitted by the backend`
    );
  }

  console.log('OpsPilot DiffReportCard live YAML contract tests passed');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
