import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import {
  SOURCE_TYPE_EXCEL,
  SOURCE_TYPE_MYSQL,
  SOURCE_TYPE_NATS,
  SOURCE_TYPE_POSTGRESQL,
  SOURCE_TYPE_PROMETHEUS,
  SOURCE_TYPE_REST_API,
  TABLE_CHART_TYPE,
  buildHydratedDatasourceFormState,
  canSaveExcelWithoutNewFile,
  getDatasourceSourceFlags,
  getPreviewFieldNames,
} from '../operateModalUtils';

describe('getDatasourceSourceFlags', () => {
  it('marks nats as neither transform nor shared connection', () => {
    assert.deepEqual(getDatasourceSourceFlags(SOURCE_TYPE_NATS), {
      isNatsSource: true,
      isRestApiSource: false,
      isPrometheusSource: false,
      isDatabaseSource: false,
      isExcelSource: false,
      supportsTransform: false,
      supportsSharedConnection: false,
    });
  });

  it('marks rest and excel as transform sources', () => {
    assert.equal(getDatasourceSourceFlags(SOURCE_TYPE_REST_API).supportsTransform, true);
    assert.equal(getDatasourceSourceFlags(SOURCE_TYPE_EXCEL).supportsTransform, true);
    assert.equal(getDatasourceSourceFlags(SOURCE_TYPE_MYSQL).supportsTransform, false);
  });

  it('marks mysql, postgresql and rest as shared-connection sources', () => {
    assert.equal(getDatasourceSourceFlags(SOURCE_TYPE_MYSQL).supportsSharedConnection, true);
    assert.equal(getDatasourceSourceFlags(SOURCE_TYPE_POSTGRESQL).supportsSharedConnection, true);
    assert.equal(getDatasourceSourceFlags(SOURCE_TYPE_REST_API).supportsSharedConnection, true);
    assert.equal(getDatasourceSourceFlags(SOURCE_TYPE_PROMETHEUS).supportsSharedConnection, false);
  });
});

describe('getPreviewFieldNames', () => {
  it('validates rest inline url and method', () => {
    assert.deepEqual(
      getPreviewFieldNames({
        sourceType: SOURCE_TYPE_REST_API,
        useSharedConnection: false,
      }),
      ['source_type', ['connection_config', 'url'], ['connection_config', 'method']],
    );
  });

  it('validates rest shared connection plus method', () => {
    assert.deepEqual(
      getPreviewFieldNames({
        sourceType: SOURCE_TYPE_REST_API,
        useSharedConnection: true,
      }),
      ['source_type', 'connection', ['connection_config', 'method']],
    );
  });

  it('adds prometheus range fields only for range queries', () => {
    assert.deepEqual(
      getPreviewFieldNames({
        sourceType: SOURCE_TYPE_PROMETHEUS,
        useSharedConnection: false,
        prometheusQueryType: 'instant',
      }),
      [
        'source_type',
        ['connection_config', 'url'],
        ['query_config', 'query'],
        ['query_config', 'query_type'],
      ],
    );
    assert.deepEqual(
      getPreviewFieldNames({
        sourceType: SOURCE_TYPE_PROMETHEUS,
        useSharedConnection: false,
        prometheusQueryType: 'range',
      }),
      [
        'source_type',
        ['connection_config', 'url'],
        ['query_config', 'query'],
        ['query_config', 'query_type'],
        ['query_config', 'time_range'],
        ['query_config', 'step'],
      ],
    );
  });

  it('falls back to source_type for nats', () => {
    assert.deepEqual(
      getPreviewFieldNames({
        sourceType: SOURCE_TYPE_NATS,
        useSharedConnection: false,
      }),
      ['source_type'],
    );
  });
});

describe('buildHydratedDatasourceFormState', () => {
  it('fills create defaults including selected group', () => {
    const state = buildHydratedDatasourceFormState(undefined, {
      selectedGroupId: 7,
      createId: () => 'id-1',
    });
    assert.equal(state.formValues.source_type, SOURCE_TYPE_NATS);
    assert.deepEqual(state.formValues.groups, [7]);
    assert.deepEqual(state.params, []);
    assert.deepEqual(state.schemaFields, []);
    assert.equal(state.excelPreview, null);
  });

  it('masks prometheus secrets and defaults chart types', () => {
    const state = buildHydratedDatasourceFormState(
      {
        id: 3,
        created_at: '',
        updated_at: '',
        created_by: '',
        updated_by: '',
        domain: '',
        updated_by_domain: '',
        name: 'prom',
        desc: '',
        source_type: SOURCE_TYPE_PROMETHEUS,
        connection_config: {
          url: 'http://prom',
          auth_type: 'basic',
          password: 'secret',
          token: 'tok',
        },
        query_config: { query: 'up', query_type: 'range', time_range: 120 },
        params: [],
        chart_type: [],
        namespaces: [],
      },
      { createId: () => 'id-1' },
    );
    const connectionConfig = state.formValues.connection_config as Record<string, unknown>;
    assert.equal(connectionConfig.password, '******');
    assert.equal(connectionConfig.token, '******');
    assert.ok(Array.isArray(state.formValues.chart_type));
    assert.ok((state.formValues.chart_type as string[]).includes('line'));
    assert.ok(state.params.length > 0);
  });

  it('restores excel imported preview and forces table chart type', () => {
    const state = buildHydratedDatasourceFormState(
      {
        id: 4,
        created_at: '',
        updated_at: '',
        created_by: '',
        updated_by: '',
        domain: '',
        updated_by_domain: '',
        name: 'excel',
        desc: '',
        source_type: SOURCE_TYPE_EXCEL,
        query_config: {
          imported_items: [{ a: 1 }],
          imported_count: 1,
          imported_fields: [{ key: 'a', title: 'A', value_type: 'number' }],
        },
        params: [],
        chart_type: ['line'],
        namespaces: [],
        field_schema: [{ key: 'a', title: 'A', value_type: 'number' }],
      },
      { createId: () => 'schema-1' },
    );
    assert.deepEqual(state.formValues.chart_type, [TABLE_CHART_TYPE]);
    assert.equal(state.excelPreview?.count, 1);
    assert.equal(state.schemaFields[0]?.id, 'schema-1');
  });
});

describe('canSaveExcelWithoutNewFile', () => {
  it('requires a new file on create', () => {
    assert.equal(
      canSaveExcelWithoutNewFile({ isEdit: false, hasLegacyImported: true }),
      false,
    );
  });

  it('allows edit when a previous successful import exists', () => {
    assert.equal(
      canSaveExcelWithoutNewFile({
        isEdit: true,
        hasLegacyImported: false,
        excelStatus: 'ready',
      }),
      true,
    );
    assert.equal(
      canSaveExcelWithoutNewFile({
        isEdit: true,
        hasLegacyImported: false,
        excelStatus: 'failed',
        hasSavedSource: true,
      }),
      true,
    );
    assert.equal(
      canSaveExcelWithoutNewFile({
        isEdit: true,
        hasLegacyImported: false,
        excelStatus: 'needs_upload',
      }),
      false,
    );
  });
});
