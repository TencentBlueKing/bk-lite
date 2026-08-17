import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import {
  buildConnectorPayload,
  shouldCreateLibraryConnectionFromForm,
  transformConfigForSourceType,
} from '../operateModalUtils';

const leftoverTransform = {
  enabled: true,
  language: 'python' as const,
  script: 'def transform(rows, params): return rows',
};

describe('transformConfigForSourceType', () => {
  it('keeps python transform for REST and Excel', () => {
    assert.equal(transformConfigForSourceType('rest_api', leftoverTransform).enabled, true);
    assert.equal(transformConfigForSourceType('excel', leftoverTransform).enabled, true);
  });

  it('disables leftover python transform for database and other types', () => {
    assert.deepEqual(transformConfigForSourceType('postgresql', leftoverTransform), {
      enabled: false,
      language: 'python',
      script: '',
    });
    assert.equal(transformConfigForSourceType('mysql', leftoverTransform).enabled, false);
    assert.equal(transformConfigForSourceType('prometheus', leftoverTransform).enabled, false);
    assert.equal(transformConfigForSourceType('nats', leftoverTransform).enabled, false);
  });
});

describe('buildConnectorPayload type-specific transform', () => {
  const t = (key: string) => key;

  it('strips enabled python transform when saving a postgresql source', () => {
    const payload = buildConnectorPayload(
      {
        source_type: 'postgresql',
        connection: 1,
        connection_mode: 'connection',
        query_config: { sql: 'SELECT 1', table: '' },
        transform_config: leftoverTransform,
      },
      { t },
    );
    assert.equal(payload.source_type, 'postgresql');
    assert.deepEqual(payload.transform_config, {
      enabled: false,
      language: 'python',
      script: '',
    });
  });

  it('keeps enabled python transform when saving a REST source', () => {
    const payload = buildConnectorPayload(
      {
        source_type: 'rest_api',
        connection_mode: 'inline',
        connection_config: {
          url: 'https://example.com/orders',
          method: 'GET',
          timeout: 10,
          headersText: '{}',
        },
        query_config: { response_path: '', paramsText: '{}', bodyText: '{}' },
        transform_config: leftoverTransform,
      },
      { t },
    );
    assert.equal(payload.source_type, 'rest_api');
    assert.equal(payload.transform_config.enabled, true);
    assert.equal(payload.transform_config.script, leftoverTransform.script);
  });
});

describe('shouldCreateLibraryConnectionFromForm', () => {
  it('creates a library connection for unsaved datasources', () => {
    assert.equal(shouldCreateLibraryConnectionFromForm(null, 'postgresql'), true);
  });

  it('creates a library connection when the saved source already has a public connection', () => {
    assert.equal(
      shouldCreateLibraryConnectionFromForm(
        { id: 1, source_type: 'rest_api', connection_id: 9 },
        'postgresql',
      ),
      true,
    );
  });

  it('creates a library connection when the form source type changed', () => {
    assert.equal(
      shouldCreateLibraryConnectionFromForm(
        { id: 1, source_type: 'rest_api' },
        'postgresql',
      ),
      true,
    );
  });

  it('extracts in place for a saved inline source of the same type', () => {
    assert.equal(
      shouldCreateLibraryConnectionFromForm(
        { id: 1, source_type: 'postgresql', connection: null, connection_id: null },
        'postgresql',
      ),
      false,
    );
  });
});
