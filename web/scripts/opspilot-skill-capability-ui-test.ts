import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const repoRoot = join(root, '..');
const readWeb = (path: string) => readFileSync(join(root, path), 'utf8');
const readRepo = (path: string) => readFileSync(join(repoRoot, path), 'utf8');

const apiSource = readWeb('src/app/opspilot/api/skill.ts');
const typeSource = readWeb('src/app/opspilot/types/skill.ts');
const toolPageSource = readWeb('src/app/opspilot/(pages)/tool/page.tsx');
const skillSettingsSource = readWeb('src/app/opspilot/(pages)/skill/detail/settings/page.tsx');
const entityListSource = readWeb('src/components/entity-list/index.tsx');
const entityTypesSource = readWeb('src/types/index.ts');
const importerSource = readRepo('server/apps/opspilot/services/skill_package/importer.py');
const runtimeSource = readRepo('server/apps/opspilot/services/skill_package/runtime.py');
const llmViewSource = readRepo('server/apps/opspilot/viewsets/llm_view.py');
const modelSource = readRepo('server/apps/opspilot/models/model_provider_mgmt.py');
const agentNodeSource = readRepo('server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py');

assert.match(typeSource, /interface SkillPackage/, 'frontend should model uploaded skill packages');
assert.match(typeSource, /skill_packages\?: SkillPackage\[\]/, 'agent details should carry selected skill packages');
assert.match(typeSource, /required_tools\?: string\[\]/, 'skill packages should declare required tools');
assert.match(typeSource, /triggers\?: string\[\]/, 'skill packages should expose runtime triggers');

assert.match(apiSource, /fetchSkillPackages/, 'frontend should fetch persisted skill packages');
assert.match(apiSource, /importSkillPackageZip/, 'frontend should import skill package ZIP files');
assert.match(apiSource, /updateSkillPackage/, 'frontend should edit skill package metadata');
assert.match(apiSource, /deleteSkillPackage/, 'frontend should delete skill packages');
assert.match(apiSource, /model_provider_mgmt\/skill_packages/, 'skill package API should use the backend viewset route');
assert.match(apiSource, /FormData/, 'ZIP upload should be sent as multipart form data');

assert.match(toolPageSource, /技能列表/, 'tool page should expose the skill package list view');
assert.match(toolPageSource, /fetchSkillPackages/, 'tool page should load real packages from the backend');
assert.match(toolPageSource, /Upload\.Dragger/, 'tool page should import ZIP packages from a modal uploader');
assert.match(toolPageSource, /importSkillPackageZip/, 'tool page should call the ZIP import API');
assert.match(toolPageSource, /updateSkillPackage/, 'tool page should support editing package metadata');
assert.match(toolPageSource, /deleteSkillPackage/, 'tool page should support package deletion');
assert.match(toolPageSource, /server\/\.skill/, 'import UI should explain server-side package storage');
assert.doesNotMatch(toolPageSource, /loadToolSkillAssets|saveToolSkillAssets|buildSkillPromptAttachments/, 'tool page should not rely on browser-only mock skill storage');
assert.doesNotMatch(toolPageSource, /审批|需审批/, 'skill package UI should not expose approval language');

assert.match(entityTypesSource, /toolbarPrefix\?: React\.ReactNode/, 'entity list should expose a left-side toolbar prefix slot');
assert.match(entityListSource, /toolbarPrefix/, 'entity list should render the shared left-side toolbar prefix');
assert.match(entityListSource, /justify-between/, 'entity list toolbar should align tabs left and search/actions right');
assert.match(toolPageSource, /renderAssetSwitcher/, 'tool page should keep tool/skill tabs on the left of the toolbar');
assert.match(toolPageSource, /renderSkillAssetControls/, 'skill search and actions should live on the right of the toolbar');

assert.match(skillSettingsSource, /技能与工具/, 'agent settings should include a skill package section');
assert.match(skillSettingsSource, /fetchSkillPackages/, 'agent settings should load available persisted packages');
assert.match(skillSettingsSource, /selectedSkillAssetKeys/, 'agent settings should select multiple skill packages');
assert.doesNotMatch(skillSettingsSource, /selectedSkillAssetKey[^s]/, 'agent settings should not keep a single selected skill state');
assert.match(skillSettingsSource, /skill_packages:/, 'saving or testing an agent should include selected packages');
assert.match(skillSettingsSource, /openSkillPicker/, 'agent settings should use a searchable package picker');
assert.match(skillSettingsSource, /handleConfirmSkillPicker/, 'agent settings should confirm multiple selected packages from the picker');
assert.match(skillSettingsSource, /handleRemoveSkillAsset/, 'agent settings should remove selected packages');
assert.match(skillSettingsSource, /missingDependencyCount/, 'agent settings should warn about missing required tools');
assert.match(skillSettingsSource, /运行时注入预览/, 'agent settings should preview package runtime injection');
assert.match(skillSettingsSource, /未选择技能包/, 'agent settings should make an empty skill selection explicit');
assert.doesNotMatch(skillSettingsSource, /getSkillCapabilityProfile|recommended \? \[recommended\]/, 'agent settings should not auto-inject an unselected recommended package');
assert.doesNotMatch(skillSettingsSource, /loadToolSkillAssets|saveToolSkillAssets|buildSkillPromptAttachments|tool_skill_asset/, 'agent settings should use backend skill packages, not local mock assets');

assert.match(importerSource, /class SkillPackageImporter/, 'backend should import skill packages from ZIP');
assert.match(importerSource, /skill\.yaml/, 'backend importer should require a package manifest');
assert.match(importerSource, /SKILL\.md/, 'backend importer should require skill instructions');
assert.match(importerSource, /server.*\.skill|DEFAULT_SKILL_PACKAGE_ROOT/, 'backend importer should store packages under the server skill directory');
assert.match(importerSource, /is_absolute\(\)|\.\./, 'backend importer should reject path traversal entries');
assert.match(importerSource, /execute_code/, 'backend importer should reject executable-code runtime declarations');

assert.match(modelSource, /class SkillPackage/, 'backend should persist uploaded skill package metadata');
assert.match(modelSource, /skill_packages = models\.JSONField/, 'agent model should persist selected skill packages');
assert.match(llmViewSource, /SkillPackageViewSet/, 'backend should expose skill package management APIs');
assert.match(llmViewSource, /def get_queryset\(self\):[\s\S]*is_enabled[\s\S]*search/, 'backend should filter skill package lists by enabled state and search keyword');
assert.match(llmViewSource, /import_zip/, 'backend should expose a ZIP import endpoint');
assert.match(llmViewSource, /partial_update/, 'backend should allow editing skill package metadata through PATCH');
assert.match(llmViewSource, /_apply_skill_packages_to_params/, 'chat execution should apply selected packages');
assert.match(runtimeSource, /select_skill_packages_for_message/, 'runtime should choose relevant selected packages by user message');
assert.match(runtimeSource, /append_matching_skill_packages_to_prompt/, 'runtime should inject matched package instructions into the prompt');
assert.match(agentNodeSource, /append_matching_skill_packages_to_prompt/, 'workflow agent nodes should use the same package injection logic');

console.log('opspilot skill package capability validation passed');
