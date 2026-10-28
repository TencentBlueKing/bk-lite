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
    assert.equal(transformConfigForSourceType('elasticsearch', leftoverTransform).enabled, false);
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

  it('clears leftover shared connection when saving excel/nats/prometheus', () => {
    const leftoverConnection = {
      connection: 9,
      connection_overrides: { path: 'orders', method: 'GET', timeout: 10 },
    };
    const excelPayload = buildConnectorPayload(
      {
        ...leftoverConnection,
        source_type: 'excel',
        connection_config: { filename: 'demo.xlsx' },
        query_config: {},
      },
      { t },
    );
    assert.equal(excelPayload.connection, null);
    assert.deepEqual(excelPayload.connection_overrides, {});

    const natsPayload = buildConnectorPayload(
      { ...leftoverConnection, source_type: 'nats' },
      { t },
    );
    assert.equal(natsPayload.connection, null);
    assert.deepEqual(natsPayload.connection_overrides, {});

    const prometheusPayload = buildConnectorPayload(
      {
        ...leftoverConnection,
        source_type: 'prometheus',
        connection_config: { url: 'http://prom.example', auth_type: 'none' },
        query_config: { query: 'up', query_type: 'instant' },
      },
      { t },
    );
    assert.equal(prometheusPayload.connection, null);
    assert.deepEqual(prometheusPayload.connection_overrides, {});
  });

  it('keeps elasticsearch query body on the datasource and overrides only the index', () => {
    const shared = buildConnectorPayload(
      {
        source_type: 'elasticsearch',
        connection: 4,
        connection_mode: 'connection',
        connection_overrides: { index: 'logs-today' },
        connection_config: { url: 'http://10.0.0.8:9200', index: 'logs' },
        query_config: {
          body: '{ "size": 20, "query": { "match_all": {} } }',
        },
        transform_config: leftoverTransform,
      },
      { t },
    );
    assert.equal(shared.connection, 4);
    assert.deepEqual(shared.connection_config, {});
    assert.deepEqual(shared.connection_overrides, { index: 'logs-today' });
    assert.deepEqual(shared.query_config.body, { size: 20, query: { match_all: {} } });
    assert.equal(shared.query_config.time_field, undefined);
    assert.equal(shared.transform_config.enabled, false);

    const inline = buildConnectorPayload(
      {
        source_type: 'elasticsearch',
        connection_mode: 'inline',
        connection_config: {
          url: 'https://10.0.0.8:9200',
          auth_type: 'api_key',
          api_key: 'id:secret',
          index: 'logs-*',
          timeout_seconds: 15,
        },
        query_config: { body: '{ "query": { "match_all": {} } }' },
      },
      { t },
    );
    assert.equal(inline.connection, null);
    assert.equal(inline.connection_config.auth_type, 'api_key');
    assert.equal(inline.connection_config.api_key, 'id:secret');
    assert.equal(inline.connection_config.index, 'logs-*');
    assert.equal(inline.connection_config.password, undefined);
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
