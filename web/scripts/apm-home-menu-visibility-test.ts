import assert from 'node:assert/strict';

/**
 * Mirrors web/src/context/permissions.tsx client-root URL ownership check.
 * App root menus (e.g. /apm/home) must stay visible when routeClientId is apm.
 */
const menuBelongsToClient = (menuUrl: string, routeClientId: string) => {
  const normalizedUrl = menuUrl.replace(/\/+$/, '') || '/';
  const clientRoot = `/${routeClientId}`;
  return normalizedUrl === clientRoot || normalizedUrl.startsWith(`${clientRoot}/`);
};

assert.equal(menuBelongsToClient('/apm', 'apm'), true, '兼容根路径仍归属 apm');
assert.equal(menuBelongsToClient('/apm/home', 'apm'), true, 'APM 首页路径必须归属 apm');
assert.equal(menuBelongsToClient('/apm/', 'apm'), true);
assert.equal(menuBelongsToClient('/apm/services', 'apm'), true);
assert.equal(menuBelongsToClient('/apm/explore/traces', 'apm'), true);
assert.equal(menuBelongsToClient('/apm/integration/add', 'apm'), true);
assert.equal(menuBelongsToClient('/monitor/event', 'apm'), false);
assert.equal(menuBelongsToClient('/job/home', 'apm'), false);

console.log('APM home menu client-root ownership checks passed');
