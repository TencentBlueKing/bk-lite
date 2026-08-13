import assert from 'node:assert/strict';
import {
  isRenderableReportDownload,
  looksLikeAttachmentDownloadUrl,
  looksLikeFakeDownloadHref,
  normalizeSafeDownloadUrl,
  rewriteAttachmentDownloadMentions,
  toAbsoluteDownloadHref,
} from '../src/app/opspilot/components/custom-chat-sse/downloadUrl';

const currentOrigin = 'https://console.example.com';

assert.equal(
  normalizeSafeDownloadUrl('/api/v1/opspilot/bot_mgmt/workflow_attachment/download/token/', { currentOrigin }),
  '/api/proxy/opspilot/bot_mgmt/workflow_attachment/download/token/'
);
assert.equal(
  normalizeSafeDownloadUrl('/api/proxy/opspilot/bot_mgmt/workflow_attachment/download/token/?next=a', { currentOrigin }),
  '/api/proxy/opspilot/bot_mgmt/workflow_attachment/download/token/?next=a'
);
assert.equal(
  normalizeSafeDownloadUrl('https://console.example.com/api/proxy/opspilot/file.docx', { currentOrigin }),
  'https://console.example.com/api/proxy/opspilot/file.docx'
);
assert.equal(
  normalizeSafeDownloadUrl('blob:https://console.example.com/attachment-id', { currentOrigin }),
  'blob:https://console.example.com/attachment-id'
);
assert.equal(
  normalizeSafeDownloadUrl('https://downloads.example.com/report.docx', {
    currentOrigin,
    allowedOrigins: ['https://downloads.example.com'],
  }),
  'https://downloads.example.com/report.docx'
);

assert.equal(normalizeSafeDownloadUrl('javascript:alert(1)', { currentOrigin }), '');
assert.equal(normalizeSafeDownloadUrl('data:text/html,<script>alert(1)</script>', { currentOrigin }), '');
assert.equal(normalizeSafeDownloadUrl('file:///etc/passwd', { currentOrigin }), '');
assert.equal(normalizeSafeDownloadUrl('https://evil.example.com/report.docx', { currentOrigin }), '');
assert.equal(normalizeSafeDownloadUrl('//evil.example.com/report.docx', { currentOrigin }), '');
assert.equal(normalizeSafeDownloadUrl('https:evil.example.com/report.docx', { currentOrigin }), '');
assert.equal(normalizeSafeDownloadUrl('report.docx', { currentOrigin }), '');
assert.equal(normalizeSafeDownloadUrl('https://user:pass@console.example.com/report.docx', { currentOrigin }), '');
assert.equal(normalizeSafeDownloadUrl('/api/proxy/opspilot/down\nload/token/', { currentOrigin }), '');
assert.equal(normalizeSafeDownloadUrl('\\evil.example.com\\report.docx', { currentOrigin }), '');

const signedUrl = '/api/proxy/opspilot/bot_mgmt/workflow_attachment/download/signed-real-token/';
const screenshotMarkdown = [
  '请点击以下链接获取月报附件：',
  '[/api/proxy/opspilot/bot_mgmt/workflow_attachment/download/加密token]',
  '(file:///api/proxy/opspilot/bot_mgmt/workflow_attachment/download/加密token/)',
].join('\n');
const rewritten = rewriteAttachmentDownloadMentions(
  screenshotMarkdown,
  [
    {
      download_id: 'attachment_1',
      filename: 'K8s_集群运维月报_2026-08.md',
      mime_type: 'text/markdown',
      file_url: signedUrl,
      received_at: 1,
    },
  ],
  { currentOrigin },
);

assert.equal(rewritten.includes('加密token'), false);
assert.equal(rewritten.includes('file:///'), false);
assert.equal(rewritten.includes('/api/proxy/opspilot/bot_mgmt/workflow_attachment/download/加密token'), false);
assert.match(
  rewritten,
  /<a href="\/api\/proxy\/opspilot\/bot_mgmt\/workflow_attachment\/download\/signed-real-token\/" download="K8s_集群运维月报_2026-08\.md">下载 K8s_集群运维月报_2026-08\.md<\/a>/,
);
assert.equal(
  looksLikeAttachmentDownloadUrl('file:///api/proxy/opspilot/bot_mgmt/workflow_attachment/download/加密token/'),
  true,
);
assert.equal(
  isRenderableReportDownload({
    download_id: 'url-only',
    filename: 'report.md',
    mime_type: 'text/markdown',
    file_url: signedUrl,
    received_at: 1,
  }),
  true,
);
assert.equal(
  isRenderableReportDownload({
    download_id: 'unsafe',
    filename: 'report.md',
    mime_type: 'text/markdown',
    file_url: 'javascript:alert(1)',
    received_at: 1,
  }),
  false,
);

const strippedWithoutDownload = rewriteAttachmentDownloadMentions(screenshotMarkdown, [], { currentOrigin });
assert.equal(strippedWithoutDownload.includes('加密token'), false);
assert.equal(strippedWithoutDownload.includes('file:///'), false);
assert.match(strippedWithoutDownload, /附件可在对话中下载/);

const rcaMarkdown = '[下载 RCA 报告](地址: http://api-lite-inner-test-833-2025-x.example/{token})';
const rcaRewritten = rewriteAttachmentDownloadMentions(
  rcaMarkdown,
  [
    {
      download_id: 'attachment_rca',
      filename: 'api-lite-inner-test-RCA-2025-08-13.md',
      mime_type: 'text/markdown',
      file_url: signedUrl,
      received_at: 1,
    },
  ],
  { currentOrigin },
);
assert.equal(rcaRewritten.includes('地址:'), false);
assert.equal(rcaRewritten.includes('{token}'), false);
assert.equal(rcaRewritten.includes('api-lite-inner-test-833-2025-x.example'), false);
assert.match(rcaRewritten, /^<a href="\/api\/proxy\/opspilot\/bot_mgmt\/workflow_attachment\/download\/signed-real-token\/"/);
assert.equal(looksLikeFakeDownloadHref('地址: http://api-lite-inner-test.example/{token}'), true);
assert.equal(
  toAbsoluteDownloadHref(signedUrl, { currentOrigin }),
  'https://console.example.com/api/proxy/opspilot/bot_mgmt/workflow_attachment/download/signed-real-token/',
);

console.log('opspilot download URL security tests passed');
