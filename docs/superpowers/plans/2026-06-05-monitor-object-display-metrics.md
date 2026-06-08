# Monitor Object Display Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `展示` action and modal prototype for configuring which metrics appear in object and child-object view lists.

**Architecture:** Keep the change inside the existing static prototype page. Add modal-specific CSS, a new modal block, static sample configuration data, and small JavaScript helpers that render object-specific display-column cards.

**Tech Stack:** Static HTML, CSS, and vanilla JavaScript in `spec/prototype/监控系统/集成/对象.html`.

---

## File Structure

- Modify: `spec/prototype/监控系统/集成/对象.html`
  - CSS: add wider display modal layout, optional object tree, display-column cards, mapping rows, and drag handle styles.
  - HTML: add `displayMetricsModal` after the existing object modal.
  - JavaScript data: add static template metric options and sample display metric configs.
  - JavaScript behavior: add open/render/switch/add/remove/reorder helpers for display metric configuration.
  - Existing table render: add `展示` before `编辑`, and make it visible for both built-in and custom objects.

No new runtime dependency is needed.

### Task 1: Add Display Modal Styles

**Files:**
- Modify: `spec/prototype/监控系统/集成/对象.html`

- [ ] **Step 1: Locate the modal CSS section**

Open `spec/prototype/监控系统/集成/对象.html` and find the existing modal styles around:

```css
/* 弹窗 */
.modal {
    background: #fff;
    border-radius: 8px;
    width: 480px;
    max-height: 80vh;
    overflow: hidden;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
}
```

- [ ] **Step 2: Add display modal CSS after `.modal-body`**

Insert this CSS after the existing `.modal-body` rule:

```css
.modal.display-modal {
    width: 860px;
    max-height: 86vh;
}

.display-modal .modal-body {
    padding: 0;
    display: flex;
    min-height: 520px;
    max-height: calc(86vh - 112px);
    overflow: hidden;
}

.display-object-tree {
    width: 180px;
    padding: 16px 12px;
    border-right: 1px solid #f0f1f5;
    background: #fafbfc;
    overflow-y: auto;
}

.display-object-tree.hidden {
    display: none;
}

.display-tree-title {
    padding: 0 8px 8px;
    font-size: 12px;
    color: #979ba5;
}

.display-tree-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 9px 10px;
    margin-bottom: 4px;
    border-radius: 4px;
    color: #63656e;
    font-size: 13px;
    cursor: pointer;
}

.display-tree-item:hover {
    background: #f0f5ff;
    color: #3a84ff;
}

.display-tree-item.active {
    background: #e1ecff;
    color: #3a84ff;
    font-weight: 500;
}

.display-config-panel {
    flex: 1;
    padding: 18px 20px;
    overflow-y: auto;
}

.display-config-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
}

.display-config-title {
    font-size: 14px;
    font-weight: 600;
    color: #313238;
}

.btn-add-display-column {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 7px 12px;
    border: 1px dashed #dcdee5;
    border-radius: 4px;
    background: #fff;
    color: #63656e;
    font-size: 13px;
    cursor: pointer;
}

.btn-add-display-column:hover {
    border-color: #3a84ff;
    color: #3a84ff;
    background: #f0f5ff;
}

.display-column-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.display-column-card {
    border: 1px solid #dcdee5;
    border-radius: 6px;
    background: #fff;
    overflow: hidden;
}

.display-column-card.dragging {
    opacity: 0.55;
    background: #f0f5ff;
}

.display-column-card.drag-over {
    border-top: 2px solid #3a84ff;
}

.display-column-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px;
    background: #fafbfc;
    border-bottom: 1px solid #f0f1f5;
}

.display-column-drag {
    width: 18px;
    color: #c4c6cc;
    cursor: grab;
    flex-shrink: 0;
}

.display-column-drag:active {
    cursor: grabbing;
}

.display-column-name {
    flex: 1;
    padding: 8px 10px;
    border: 1px solid #dcdee5;
    border-radius: 4px;
    font-size: 13px;
}

.display-column-name:focus {
    outline: none;
    border-color: #3a84ff;
}

.btn-remove-display-column,
.btn-remove-mapping {
    width: 28px;
    height: 28px;
    border: none;
    border-radius: 4px;
    background: #f5f7fa;
    color: #979ba5;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
}

.btn-remove-display-column:hover,
.btn-remove-mapping:hover {
    background: #ffebeb;
    color: #ea3636;
}

.mapping-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px;
}

.mapping-row {
    display: grid;
    grid-template-columns: minmax(160px, 1fr) minmax(180px, 1fr) 28px;
    gap: 8px;
    align-items: center;
}

.mapping-row select {
    width: 100%;
    padding: 8px 10px;
    border: 1px solid #dcdee5;
    border-radius: 4px;
    background: #fff;
    font-size: 13px;
    color: #313238;
}

.btn-add-mapping {
    align-self: flex-start;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin: 0 12px 12px;
    padding: 7px 10px;
    border: 1px dashed #dcdee5;
    border-radius: 4px;
    background: #fff;
    color: #63656e;
    font-size: 13px;
    cursor: pointer;
}

.btn-add-mapping:hover {
    border-color: #3a84ff;
    color: #3a84ff;
    background: #f0f5ff;
}
```

- [ ] **Step 3: Verify no visual styles changed outside the new modal**

Run:

```bash
git diff -- spec/prototype/监控系统/集成/对象.html
```

Expected: the diff only adds new selectors prefixed with `display-`, `btn-add-display-column`, `btn-remove-display-column`, `btn-remove-mapping`, and `btn-add-mapping`.

### Task 2: Add the Display Metrics Modal Markup

**Files:**
- Modify: `spec/prototype/监控系统/集成/对象.html`

- [ ] **Step 1: Locate the existing object modal**

Find the block that starts with:

```html
<!-- 新建对象弹窗 -->
<div class="modal-overlay" id="addObjectModal">
```

Scroll to the end of that modal, immediately before:

```html
<script>
```

- [ ] **Step 2: Insert the new modal before `<script>`**

Add this block immediately before the page script:

```html
<!-- 展示指标配置弹窗 -->
<div class="modal-overlay" id="displayMetricsModal">
    <div class="modal display-modal">
        <div class="modal-header">
            <span class="modal-title" id="displayMetricsTitle">展示指标配置</span>
            <div class="modal-close" onclick="closeModal('displayMetricsModal')">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"/>
                    <line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
            </div>
        </div>
        <div class="modal-body">
            <div class="display-object-tree hidden" id="displayObjectTree"></div>
            <div class="display-config-panel">
                <div class="display-config-header">
                    <div class="display-config-title" id="displayConfigTitle">展示列配置</div>
                    <button type="button" class="btn-add-display-column" onclick="addDisplayColumn()">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="12" y1="5" x2="12" y2="19"/>
                            <line x1="5" y1="12" x2="19" y2="12"/>
                        </svg>
                        添加展示列
                    </button>
                </div>
                <div class="display-column-list" id="displayColumnList"></div>
            </div>
        </div>
        <div class="modal-footer">
            <button class="btn-cancel" onclick="closeModal('displayMetricsModal')">取消</button>
            <button class="btn-confirm" onclick="closeModal('displayMetricsModal')">确定</button>
        </div>
    </div>
</div>
```

- [ ] **Step 3: Verify modal IDs are unique**

Run:

```bash
rg -n "displayMetricsModal|displayObjectTree|displayColumnList|displayMetricsTitle|displayConfigTitle" spec/prototype/监控系统/集成/对象.html
```

Expected: each ID appears in the new modal and later JavaScript references only.

### Task 3: Add Static Display Metric Data

**Files:**
- Modify: `spec/prototype/监控系统/集成/对象.html`

- [ ] **Step 1: Locate `objectData` and current state**

In the page script, find:

```js
// 对象数据
const objectData = {
```

Then find:

```js
let currentType = '操作系统';
```

- [ ] **Step 2: Add sample template metric options before `let currentType`**

Insert this block immediately before `let currentType = '操作系统';`:

```js
const templateMetricOptions = {
    '模版A': ['CPU使用率', '内存使用率', '磁盘使用率'],
    '模版B': ['cpu_usage', 'mem_usage', 'disk_usage'],
    'K8s模版': ['pod_cpu_usage', 'pod_memory_usage', 'node_cpu_usage']
};
```

- [ ] **Step 3: Add sample display metric configs after template options**

Insert this block immediately after `templateMetricOptions`:

```js
const displayMetricConfigs = {
    host: {
        host: [
            {
                name: 'CPU使用率',
                mappings: [
                    { template: '模版A', metric: 'CPU使用率' },
                    { template: '模版B', metric: 'cpu_usage' }
                ]
            },
            {
                name: '内存使用率',
                mappings: [
                    { template: '模版A', metric: '内存使用率' },
                    { template: '模版B', metric: 'mem_usage' }
                ]
            }
        ]
    },
    kubernetes: {
        kubernetes: [
            {
                name: '集群CPU使用率',
                mappings: [
                    { template: 'K8s模版', metric: 'node_cpu_usage' }
                ]
            }
        ],
        sub_pod: [
            {
                name: 'Pod CPU使用率',
                mappings: [
                    { template: 'K8s模版', metric: 'pod_cpu_usage' }
                ]
            },
            {
                name: 'Pod内存使用率',
                mappings: [
                    { template: 'K8s模版', metric: 'pod_memory_usage' }
                ]
            }
        ],
        sub_node: [
            {
                name: 'Node CPU使用率',
                mappings: [
                    { template: 'K8s模版', metric: 'node_cpu_usage' }
                ]
            }
        ]
    },
    custom_obj_2: {
        custom_obj_2: [
            {
                name: 'CPU使用率',
                mappings: [
                    { template: '模版A', metric: 'CPU使用率' },
                    { template: '模版B', metric: 'cpu_usage' }
                ]
            }
        ],
        sub_vm: [
            {
                name: '虚拟机CPU使用率',
                mappings: [
                    { template: '模版A', metric: 'CPU使用率' }
                ]
            }
        ],
        sub_datastore: [
            {
                name: '存储使用率',
                mappings: [
                    { template: '模版B', metric: 'disk_usage' }
                ]
            }
        ]
    }
};

let currentDisplayObject = null;
let currentDisplayTargetId = '';
```

- [ ] **Step 4: Add child objects to Kubernetes sample data**

In `objectData['容器']`, replace the Kubernetes object:

```js
{ id: 20, objectId: 'kubernetes', name: 'Kubernetes', icon: 'grid', source: 'custom', visible: true }
```

with:

```js
{ id: 20, objectId: 'kubernetes', name: 'Kubernetes', icon: 'grid', source: 'custom', visible: true, subObjects: [
    { id: 'sub_pod', name: 'Pod' },
    { id: 'sub_node', name: 'Node' }
] }
```

- [ ] **Step 5: Verify the static data anchors are present**

Run:

```bash
rg -n "templateMetricOptions|displayMetricConfigs|currentDisplayObject|currentDisplayTargetId|sub_pod|sub_node" spec/prototype/监控系统/集成/对象.html
```

Expected: the output shows the template options, display config object, display state variables, and Kubernetes child object ids.

### Task 4: Add Display Modal JavaScript Helpers

**Files:**
- Modify: `spec/prototype/监控系统/集成/对象.html`

- [ ] **Step 1: Add helper functions before `// 切换对象可见性`**

Find:

```js
        // 切换对象可见性
        function toggleObjectVisibility(element, objectId) {
```

Insert this block immediately before it:

```js
        function findObjectById(objectId) {
            const allObjects = Object.values(objectData).flat();
            return allObjects.find(obj => obj.id === objectId);
        }

        function getDisplayTargets(obj) {
            const targets = [{ id: obj.objectId, name: obj.name, type: '主对象' }];
            (obj.subObjects || []).forEach(sub => {
                targets.push({ id: sub.id, name: sub.name, type: '子对象' });
            });
            return targets;
        }

        function ensureDisplayConfig(objectKey, targetId) {
            if (!displayMetricConfigs[objectKey]) {
                displayMetricConfigs[objectKey] = {};
            }
            if (!displayMetricConfigs[objectKey][targetId]) {
                displayMetricConfigs[objectKey][targetId] = [];
            }
            return displayMetricConfigs[objectKey][targetId];
        }

        function openDisplayMetricsModal(objectId) {
            const obj = findObjectById(objectId);
            if (!obj) return;

            currentDisplayObject = obj;
            currentDisplayTargetId = obj.objectId;
            ensureDisplayConfig(obj.objectId, obj.objectId);

            document.getElementById('displayMetricsTitle').textContent = `展示指标配置 - ${obj.name}`;
            renderDisplayObjectTree();
            renderDisplayColumns();
            document.getElementById('displayMetricsModal').classList.add('show');
        }

        function renderDisplayObjectTree() {
            const tree = document.getElementById('displayObjectTree');
            const targets = getDisplayTargets(currentDisplayObject);

            if (targets.length <= 1) {
                tree.classList.add('hidden');
                tree.innerHTML = '';
                return;
            }

            tree.classList.remove('hidden');
            tree.innerHTML = `
                <div class="display-tree-title">配置对象</div>
                ${targets.map(target => `
                    <div class="display-tree-item ${target.id === currentDisplayTargetId ? 'active' : ''}" onclick="switchDisplayTarget('${target.id}')">
                        <span>${target.name}</span>
                        <span>${target.type}</span>
                    </div>
                `).join('')}
            `;
        }

        function switchDisplayTarget(targetId) {
            currentDisplayTargetId = targetId;
            ensureDisplayConfig(currentDisplayObject.objectId, targetId);
            renderDisplayObjectTree();
            renderDisplayColumns();
        }

        function getCurrentDisplayColumns() {
            if (!currentDisplayObject) return [];
            return ensureDisplayConfig(currentDisplayObject.objectId, currentDisplayTargetId);
        }

        function renderDisplayColumns() {
            const list = document.getElementById('displayColumnList');
            const target = getDisplayTargets(currentDisplayObject).find(item => item.id === currentDisplayTargetId);
            const columns = getCurrentDisplayColumns();

            document.getElementById('displayConfigTitle').textContent = `${target ? target.name : ''}展示列配置`;

            if (columns.length === 0) {
                list.innerHTML = `
                    <div class="empty-state" style="padding: 48px 20px;">
                        <div class="empty-icon">📊</div>
                        <div class="empty-text">暂无展示列，点击"添加展示列"配置</div>
                    </div>
                `;
                return;
            }

            list.innerHTML = columns.map((column, columnIndex) => `
                <div class="display-column-card" draggable="true" data-column-index="${columnIndex}">
                    <div class="display-column-header">
                        <div class="display-column-drag">
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                                <circle cx="9" cy="6" r="1.5"/>
                                <circle cx="15" cy="6" r="1.5"/>
                                <circle cx="9" cy="12" r="1.5"/>
                                <circle cx="15" cy="12" r="1.5"/>
                                <circle cx="9" cy="18" r="1.5"/>
                                <circle cx="15" cy="18" r="1.5"/>
                            </svg>
                        </div>
                        <input class="display-column-name" value="${column.name}" placeholder="请输入展示列名称" onchange="updateDisplayColumnName(${columnIndex}, this.value)">
                        <button type="button" class="btn-remove-display-column" onclick="removeDisplayColumn(${columnIndex})">
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="18" y1="6" x2="6" y2="18"/>
                                <line x1="6" y1="6" x2="18" y2="18"/>
                            </svg>
                        </button>
                    </div>
                    <div class="mapping-list">
                        ${column.mappings.map((mapping, mappingIndex) => renderMappingRow(columnIndex, mappingIndex, mapping)).join('')}
                    </div>
                    <button type="button" class="btn-add-mapping" onclick="addMetricMapping(${columnIndex})">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="12" y1="5" x2="12" y2="19"/>
                            <line x1="5" y1="12" x2="19" y2="12"/>
                        </svg>
                        添加指标
                    </button>
                </div>
            `).join('');

            initDisplayColumnDragAndDrop();
        }

        function renderMappingRow(columnIndex, mappingIndex, mapping) {
            const templateOptions = Object.keys(templateMetricOptions).map(template => `
                <option value="${template}" ${template === mapping.template ? 'selected' : ''}>${template}</option>
            `).join('');
            const metrics = templateMetricOptions[mapping.template] || [];
            const metricOptions = metrics.map(metric => `
                <option value="${metric}" ${metric === mapping.metric ? 'selected' : ''}>${metric}</option>
            `).join('');

            return `
                <div class="mapping-row">
                    <select onchange="updateMetricTemplate(${columnIndex}, ${mappingIndex}, this.value)">
                        ${templateOptions}
                    </select>
                    <select onchange="updateMetricValue(${columnIndex}, ${mappingIndex}, this.value)">
                        ${metricOptions}
                    </select>
                    <button type="button" class="btn-remove-mapping" onclick="removeMetricMapping(${columnIndex}, ${mappingIndex})">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="18" y1="6" x2="6" y2="18"/>
                            <line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                    </button>
                </div>
            `;
        }

        function addDisplayColumn() {
            const columns = getCurrentDisplayColumns();
            columns.push({
                name: '新展示列',
                mappings: [
                    { template: '模版A', metric: 'CPU使用率' }
                ]
            });
            renderDisplayColumns();
        }

        function removeDisplayColumn(columnIndex) {
            getCurrentDisplayColumns().splice(columnIndex, 1);
            renderDisplayColumns();
        }

        function updateDisplayColumnName(columnIndex, value) {
            getCurrentDisplayColumns()[columnIndex].name = value || '未命名展示列';
        }

        function addMetricMapping(columnIndex) {
            getCurrentDisplayColumns()[columnIndex].mappings.push({ template: '模版A', metric: 'CPU使用率' });
            renderDisplayColumns();
        }

        function removeMetricMapping(columnIndex, mappingIndex) {
            getCurrentDisplayColumns()[columnIndex].mappings.splice(mappingIndex, 1);
            renderDisplayColumns();
        }

        function updateMetricTemplate(columnIndex, mappingIndex, template) {
            const mapping = getCurrentDisplayColumns()[columnIndex].mappings[mappingIndex];
            mapping.template = template;
            mapping.metric = (templateMetricOptions[template] || [''])[0];
            renderDisplayColumns();
        }

        function updateMetricValue(columnIndex, mappingIndex, metric) {
            getCurrentDisplayColumns()[columnIndex].mappings[mappingIndex].metric = metric;
        }

        function initDisplayColumnDragAndDrop() {
            const cards = document.querySelectorAll('.display-column-card');
            let draggedIndex = null;

            cards.forEach(card => {
                card.addEventListener('dragstart', function() {
                    draggedIndex = Number(this.dataset.columnIndex);
                    this.classList.add('dragging');
                });

                card.addEventListener('dragend', function() {
                    this.classList.remove('dragging');
                    document.querySelectorAll('.display-column-card').forEach(item => item.classList.remove('drag-over'));
                });

                card.addEventListener('dragover', function(event) {
                    event.preventDefault();
                    this.classList.add('drag-over');
                });

                card.addEventListener('dragleave', function() {
                    this.classList.remove('drag-over');
                });

                card.addEventListener('drop', function(event) {
                    event.preventDefault();
                    const targetIndex = Number(this.dataset.columnIndex);
                    if (draggedIndex === null || draggedIndex === targetIndex) return;

                    const columns = getCurrentDisplayColumns();
                    const [draggedColumn] = columns.splice(draggedIndex, 1);
                    columns.splice(targetIndex, 0, draggedColumn);
                    renderDisplayColumns();
                });
            });
        }
```

- [ ] **Step 2: Verify helper names are unique**

Run:

```bash
rg -n "function (findObjectById|getDisplayTargets|ensureDisplayConfig|openDisplayMetricsModal|renderDisplayObjectTree|switchDisplayTarget|getCurrentDisplayColumns|renderDisplayColumns|renderMappingRow|addDisplayColumn|removeDisplayColumn|updateDisplayColumnName|addMetricMapping|removeMetricMapping|updateMetricTemplate|updateMetricValue|initDisplayColumnDragAndDrop)" spec/prototype/监控系统/集成/对象.html
```

Expected: one definition for each helper.

### Task 5: Add `展示` to the Object Table Actions

**Files:**
- Modify: `spec/prototype/监控系统/集成/对象.html`

- [ ] **Step 1: Update the static initial row**

Find the initial hard-coded row action:

```html
<div class="action-buttons">
    <button class="btn-action" onclick="openEditObjectModal()">编辑</button>
</div>
```

Replace it with:

```html
<div class="action-buttons">
    <button class="btn-action" onclick="openDisplayMetricsModal(1)">展示</button>
    <button class="btn-action" onclick="openEditObjectModal()">编辑</button>
</div>
```

- [ ] **Step 2: Update `renderObjectTable` generated actions**

Find this generated action block:

```js
<div class="action-buttons">
    ${obj.source === 'custom' ? '<button class="btn-action" onclick="openEditObjectModal(' + obj.id + ')">编辑</button><button class="btn-action btn-delete" onclick="deleteObject(' + obj.id + ')">删除</button>' : ''}
</div>
```

Replace it with:

```js
<div class="action-buttons">
    <button class="btn-action" onclick="openDisplayMetricsModal(${obj.id})">展示</button>
    ${obj.source === 'custom' ? '<button class="btn-action" onclick="openEditObjectModal(' + obj.id + ')">编辑</button><button class="btn-action btn-delete" onclick="deleteObject(' + obj.id + ')">删除</button>' : ''}
</div>
```

- [ ] **Step 3: Widen the operation column**

Find:

```html
<th style="width: 160px;">操作</th>
```

Replace it with:

```html
<th style="width: 220px;">操作</th>
```

- [ ] **Step 4: Verify action labels**

Run:

```bash
rg -n "openDisplayMetricsModal|展示 / 编辑 / 删除|展示" spec/prototype/监控系统/集成/对象.html
```

Expected: `openDisplayMetricsModal` appears in the static row, generated row actions, and function definition. The visible `展示` label appears in both table action locations and the display modal content.

### Task 6: Manual Prototype Verification

**Files:**
- Verify: `spec/prototype/监控系统/集成/对象.html`

- [ ] **Step 1: Start a static file server from the repository root**

Run:

```bash
python3 -m http.server 4173
```

Expected: terminal prints `Serving HTTP on :: port 4173` or `Serving HTTP on 0.0.0.0 port 4173`.

- [ ] **Step 2: Open the prototype URL**

Open:

```text
http://localhost:4173/spec/prototype/%E7%9B%91%E6%8E%A7%E7%B3%BB%E7%BB%9F/%E9%9B%86%E6%88%90/%E5%AF%B9%E8%B1%A1.html
```

Expected: the object management prototype loads.

- [ ] **Step 3: Verify table actions**

In the `操作系统` tab:

```text
主机 row: 展示 is visible.
自定义对象 rows: 展示 / 编辑 / 删除 are visible.
```

In the `数据库` tab:

```text
MySQL row: 展示 is visible.
MySQL row: 编辑 and 删除 are not visible.
TiDB row: 展示 / 编辑 / 删除 are visible.
```

- [ ] **Step 4: Verify object without child objects**

Click `展示` on `主机`.

Expected:

```text
Modal title: 展示指标配置 - 主机
No left object tree is visible.
Right panel title: 主机展示列配置
CPU使用率 and 内存使用率 cards are visible.
CPU使用率 includes 模版A / CPU使用率 and 模版B / cpu_usage.
```

- [ ] **Step 5: Verify object with child objects**

Switch to `容器`, click `展示` on `Kubernetes`.

Expected:

```text
Modal title: 展示指标配置 - Kubernetes
Left object tree shows Kubernetes, Pod, Node.
Clicking Pod changes the right panel title to Pod展示列配置.
Clicking Node changes the right panel title to Node展示列配置.
```

- [ ] **Step 6: Verify edit interactions**

Inside the display modal:

```text
Click 添加展示列: a new card named 新展示列 appears.
Change the new card name: the input accepts the new value.
Click 添加指标: a new 模版A / CPU使用率 mapping row appears.
Change the template to 模版B: the metric select changes to cpu_usage / mem_usage / disk_usage.
Click the mapping remove button: that mapping row disappears.
Click the column remove button: that display column disappears.
Drag one display column above another: the card order changes.
Click 取消: modal closes.
Open again and click 确定: modal closes.
Open again and click the close icon: modal closes.
```

- [ ] **Step 7: Stop the static server**

Press `Ctrl+C` in the static server terminal.

Expected: the server exits and no long-running task remains.

### Task 7: Final Review and Commit

**Files:**
- Modify: `spec/prototype/监控系统/集成/对象.html`

- [ ] **Step 1: Review final diff**

Run:

```bash
git diff -- spec/prototype/监控系统/集成/对象.html
```

Expected:

```text
The diff adds display modal CSS.
The diff adds the display metrics modal.
The diff adds static template/config data.
The diff adds display modal JavaScript helpers.
The diff adds 展示 before 编辑 in object row actions.
No unrelated prototype pages are changed.
```

- [ ] **Step 2: Check changed files**

Run:

```bash
git status --short
```

Expected:

```text
 M spec/prototype/监控系统/集成/对象.html
```

- [ ] **Step 3: Commit the implementation**

Run:

```bash
git add spec/prototype/监控系统/集成/对象.html
git commit -m "feat: add object display metrics prototype"
```

Expected: git creates one commit containing only the prototype implementation.

## Self-Review

- Spec coverage: the plan covers the `展示` entry for all objects, optional object tree, display-column cards, multiple template metric mappings, column ordering, and the agreed non-goals.
- Placeholder scan: the plan contains no deferred implementation placeholders.
- Type consistency: the plan consistently uses `displayMetricConfigs`, `templateMetricOptions`, `currentDisplayObject`, `currentDisplayTargetId`, `openDisplayMetricsModal`, and `renderDisplayColumns`.
