import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const checkTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/CheckTab.tsx'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

for (const key of ['checkStatusAll', 'checkTypeAll']) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

assert.match(checkTab, /Select/);
assert.match(checkTab, /const \[statusFilter,\s*setStatusFilter\] = useState\('open'\)/);
assert.match(checkTab, /const \[checkTypeFilter,\s*setCheckTypeFilter\] = useState\(''\)/);
assert.match(checkTab, /fetchCheckItems\(kbId,\s*\{[\s\S]*status:\s*statusFilter \|\| undefined[\s\S]*check_type:\s*checkTypeFilter \|\| undefined/);
assert.match(checkTab, /const statusOptions = useMemo/);
assert.match(checkTab, /const checkTypeOptions = useMemo/);
assert.match(checkTab, /handleStatusFilterChange/);
assert.match(checkTab, /handleCheckTypeFilterChange/);
assert.match(checkTab, /t\('wiki\.checkStatusAll'\)/);
assert.match(checkTab, /t\('wiki\.checkTypeAll'\)/);

console.log('wiki check filter validation passed');
