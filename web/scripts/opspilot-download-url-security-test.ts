import assert from 'node:assert/strict';
import { normalizeSafeDownloadUrl } from '../src/app/opspilot/components/custom-chat-sse/downloadUrl';

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

console.log('opspilot download URL security tests passed');
