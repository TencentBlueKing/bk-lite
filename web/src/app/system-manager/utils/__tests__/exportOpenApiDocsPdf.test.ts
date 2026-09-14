import { describe, expect, it } from 'vitest';
import type { OpenAPIDocRow } from '@/app/system-manager/utils/openapiDocs';
import {
  buildOpenApiDocsExportHtml,
  buildOpenApiDocsPdfFilename,
  choosePageCut,
} from '@/app/system-manager/utils/exportOpenApiDocsPdf';

const labels = {
  title: '接口文档',
  catalog: '接口目录',
  generatedAt: '2026-09-10 15:30',
  totalCount: '共 2 个接口',
  kind: '类型',
  authHeader: '认证机制',
  authHeaderDesc: 'Authorization: Bearer <API_TOKEN>',
  internal: '内部',
  external: '外部',
  service: '服务',
  method: '方法',
  path: '路径',
  summary: '摘要',
  fieldName: '字段',
  fieldType: '类型',
  required: '必填',
  range: '范围',
  default: '默认值',
  choices: '取值',
  yes: '是',
  no: '否',
  noParams: '该接口无需在请求体传递参数',
  entryPrefix: '入口前缀',
  docUrl: '文档链接',
  noDocUrl: '无文档链接',
  externalDocHint: '请访问外部官方文档',
  permissionControl: '权限控制',
  unrestricted: '无特殊限制',
  orgScope: '组织范围',
  tabExample: '调用示例',
  inject: (value: string) => `inject:${value}`,
};

const internalRow: OpenAPIDocRow = {
  key: 'internal:GET:/openapi/v1/cmdb/model',
  kind: 'internal',
  service: 'cmdb',
  method: 'GET',
  path: '/openapi/v1/cmdb/model',
  summary: '查询模型详情 <script>',
  docUrl: '',
  inject: 'team_list',
  permission: 'cmdb-View',
  requestSchema: {
    node_id: { type: 'integer', required: true },
    page: { type: 'integer', required: false, default: 1 },
  },
  searchText: '',
};

const choiceRow: OpenAPIDocRow = {
  ...internalRow,
  key: 'internal:GET:/openapi/v1/patch-mgmt/module-data',
  method: 'GET',
  path: '/openapi/v1/patch-mgmt/module-data',
  service: 'patch-mgmt',
  summary: '模块数据',
  requestSchema: {
    module: { type: 'choice', required: true, choices: ['patch_target'] },
  },
};

const externalRow: OpenAPIDocRow = {
  key: 'external:itsm',
  kind: 'external',
  service: 'itsm',
  method: '',
  path: '/openapi/v1/itsm',
  summary: '',
  docUrl: 'https://itsm.example.com/docs/swagger.json',
  inject: '',
  permission: '',
  requestSchema: {},
  searchText: '',
};

describe('buildOpenApiDocsExportHtml', () => {
  it('renders catalog index, escaped summary, and default column only when present', () => {
    const html = buildOpenApiDocsExportHtml([internalRow], labels);

    expect(html).toContain('接口目录');
    expect(html).toContain('/openapi/v1/cmdb/model');
    expect(html).toContain('cmdb-View');
    expect(html).toContain('inject:team_list');
    expect(html).toContain('查询模型详情 &lt;script&gt;');
    expect(html).not.toContain('查询模型详情 <script>');
    expect(html).toContain('默认值');
    expect(html).toContain('>1<');
    expect(html).not.toContain('取值');
    expect(html).not.toContain('<th>范围</th>');
    expect(html).toContain('curl -X GET');
  });

  it('renders choices column when a field has choices, without fabricating defaults', () => {
    const html = buildOpenApiDocsExportHtml([choiceRow], labels);

    expect(html).toContain('取值');
    expect(html).toContain('patch_target');
    expect(html).not.toContain('默认值');
    expect(html).not.toContain('<th>范围</th>');
  });

  it('renders range column only when a field has min or max', () => {
    const html = buildOpenApiDocsExportHtml(
      [
        {
          ...internalRow,
          requestSchema: {
            timeout: {
              type: 'integer',
              required: false,
              default: 30,
              min_value: 1,
              max_value: 86400,
            },
            group_id: { type: 'integer', required: true, min_value: 1 },
          },
        },
      ],
      labels,
    );

    expect(html).toContain('<th>范围</th>');
    expect(html).toContain('1 ~ 86400');
    expect(html).toContain('≥ 1');
  });

  it('renders external services with doc url and without curl', () => {
    const html = buildOpenApiDocsExportHtml([externalRow], labels);

    expect(html).toContain('https://itsm.example.com/docs/swagger.json');
    expect(html).toContain('请访问外部官方文档');
    expect(html).toContain('EXT');
    expect(html).not.toContain('curl -X');
  });

  it('splits a long catalog index into multiple capture blocks', () => {
    const rows = Array.from({ length: 45 }, (_, index) => ({
      ...internalRow,
      key: `internal:GET:/openapi/v1/cmdb/p${index}`,
      path: `/openapi/v1/cmdb/p${index}`,
    }));
    const html = buildOpenApiDocsExportHtml(rows, labels);
    expect((html.match(/<th>方法<\/th>/g) || []).length).toBe(3);
    expect(html).toContain('data-pdf-line');
  });
});

describe('choosePageCut', () => {
  it('cuts at the last table row that still fits the page', () => {
    expect(choosePageCut(0, 100, 400, [30, 80, 150, 220])).toBe(80);
  });

  it('does not leave leftover content when the remainder fits', () => {
    expect(choosePageCut(0, 500, 400, [30, 80, 150])).toBe(400);
  });

  it('returns start when the next row is taller than remaining space', () => {
    expect(choosePageCut(90, 100, 400, [30, 80, 150])).toBe(90);
  });
});

describe('buildOpenApiDocsPdfFilename', () => {
  it('uses a stable dated filename', () => {
    expect(buildOpenApiDocsPdfFilename(new Date(2026, 8, 10))).toBe('openapi-docs-2026-09-10');
  });
});
