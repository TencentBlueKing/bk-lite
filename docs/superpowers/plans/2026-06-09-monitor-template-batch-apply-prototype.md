# Monitor Template Batch Apply Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the monitor event template HTML prototype so users can select multiple templates and apply them through a 3-step batch wizard.

**Architecture:** Keep the prototype as a single static HTML file. Add selection controls to template cards, a sticky batch action bar, a modal wizard for template confirmation, asset selection, shared settings, and a result state. Use local JavaScript state to drive selection, wizard navigation, preview counts, search, and success feedback.

**Tech Stack:** Static HTML, CSS, vanilla JavaScript, existing prototype visual language in `spec/prototype/监控系统/事件/模版.html`.

---

### Task 1: Add Multi-Select Controls To Template Cards

**Files:**
- Modify: `spec/prototype/监控系统/事件/模版.html`

- [ ] **Step 1: Add card selection CSS**

Add CSS classes for checkbox chips, selected card state, and single use buttons inside the existing `<style>` block near `.template-card`.

```css
.template-card {
    position: relative;
}

.template-check {
    position: absolute;
    top: 12px;
    right: 12px;
    width: 18px;
    height: 18px;
    border: 1px solid #c6ccd6;
    border-radius: 4px;
    background: #fff;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: #fff;
}

.template-card.selected .template-check {
    border-color: #2f63f6;
    background: #2f63f6;
}

.template-card.selected .template-check::after {
    content: "";
    width: 8px;
    height: 4px;
    border-left: 2px solid #fff;
    border-bottom: 2px solid #fff;
    transform: rotate(-45deg) translate(1px, -1px);
}

.card-actions {
    margin-top: 14px;
}

.link-button {
    border: 0;
    background: transparent;
    color: #1f66ff;
    cursor: pointer;
    font-size: 13px;
    padding: 0;
}
```

- [ ] **Step 2: Add selection markup to each card**

Inside each `<article class="template-card">`, add a check indicator and a lightweight single-template action. Repeat for all 12 cards.

```html
<span class="template-check" aria-hidden="true"></span>
...
<div class="card-actions">
    <button class="link-button single-use" type="button">使用</button>
</div>
```

- [ ] **Step 3: Update card click JavaScript**

Replace the old selected-card-only click behavior with multi-select behavior. Use a `selectedTemplates` set keyed by card title.

```javascript
const selectedTemplates = new Set();

function getCardTitle(card) {
    return card.querySelector(".card-title").textContent.trim();
}

function toggleCard(card) {
    const title = getCardTitle(card);
    if (selectedTemplates.has(title)) {
        selectedTemplates.delete(title);
        card.classList.remove("selected");
    } else {
        selectedTemplates.add(title);
        card.classList.add("selected");
    }
    updateBatchBar();
}

cards.forEach((card) => {
    card.addEventListener("click", (event) => {
        if (event.target.classList.contains("single-use")) {
            event.stopPropagation();
            selectedTemplates.clear();
            cards.forEach((item) => item.classList.remove("selected"));
            selectedTemplates.add(getCardTitle(card));
            card.classList.add("selected");
            openWizard();
            return;
        }
        toggleCard(card);
    });
});
```

- [ ] **Step 4: Verify manually**

Open `spec/prototype/监控系统/事件/模版.html` in the browser. Click three cards.

Expected:
- Each clicked card stays selected.
- Clicking a selected card again removes selection.
- The `使用` action selects only that card and opens the wizard.

### Task 2: Add Sticky Batch Action Bar

**Files:**
- Modify: `spec/prototype/监控系统/事件/模版.html`

- [ ] **Step 1: Add batch bar CSS**

Add CSS for a sticky bottom action bar inside the content area.

```css
.batch-bar {
    position: sticky;
    bottom: 0;
    display: none;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-top: 24px;
    padding: 14px 18px;
    border: 1px solid #d7e4ff;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.96);
    box-shadow: 0 -4px 18px rgba(31, 45, 61, 0.08);
}

.batch-bar.show {
    display: flex;
}

.batch-actions {
    display: flex;
    align-items: center;
    gap: 10px;
}

.primary-button,
.secondary-button {
    height: 32px;
    padding: 0 16px;
    border-radius: 4px;
    cursor: pointer;
}

.primary-button {
    border: 1px solid #2f63f6;
    background: #2f63f6;
    color: #fff;
}

.secondary-button {
    border: 1px solid #d7dce5;
    background: #fff;
    color: #344054;
}
```

- [ ] **Step 2: Add batch bar markup**

Place this after `<div class="empty" id="emptyState">暂无匹配的模板</div>` inside the content section.

```html
<div class="batch-bar" id="batchBar">
    <div>
        已选择 <strong id="selectedCount">0</strong> 个模板
        <span class="muted">将按模板数创建策略，每条策略覆盖同一批资产</span>
    </div>
    <div class="batch-actions">
        <button class="secondary-button" id="selectAllButton" type="button">全选当前对象模板</button>
        <button class="secondary-button" id="clearSelectionButton" type="button">清空</button>
        <button class="primary-button" id="batchApplyButton" type="button">批量应用</button>
    </div>
</div>
```

- [ ] **Step 3: Add batch bar JavaScript**

Add functions to update count, select all visible cards, clear selection, and open the wizard.

```javascript
const batchBar = document.getElementById("batchBar");
const selectedCount = document.getElementById("selectedCount");
const selectAllButton = document.getElementById("selectAllButton");
const clearSelectionButton = document.getElementById("clearSelectionButton");
const batchApplyButton = document.getElementById("batchApplyButton");

function updateBatchBar() {
    selectedCount.textContent = selectedTemplates.size;
    batchBar.classList.toggle("show", selectedTemplates.size > 0);
}

selectAllButton.addEventListener("click", () => {
    cards.forEach((card) => {
        if (getComputedStyle(card).display !== "none") {
            selectedTemplates.add(getCardTitle(card));
            card.classList.add("selected");
        }
    });
    updateBatchBar();
});

clearSelectionButton.addEventListener("click", () => {
    selectedTemplates.clear();
    cards.forEach((card) => card.classList.remove("selected"));
    updateBatchBar();
});

batchApplyButton.addEventListener("click", openWizard);
```

- [ ] **Step 4: Verify manually**

Open the prototype and select two templates.

Expected:
- Batch bar appears.
- Count is `2`.
- `清空` clears all selections.
- `全选当前对象模板` selects all currently visible cards.

### Task 3: Add Batch Apply Wizard Modal

**Files:**
- Modify: `spec/prototype/监控系统/事件/模版.html`

- [ ] **Step 1: Add wizard CSS**

Add CSS for modal shell, step navigation, template list, asset checklist, shared configuration form, preview table, and result panel.

```css
.modal-mask {
    position: fixed;
    inset: 0;
    display: none;
    align-items: center;
    justify-content: center;
    background: rgba(15, 23, 42, 0.35);
    z-index: 50;
}

.modal-mask.show {
    display: flex;
}

.wizard {
    width: min(980px, calc(100vw - 80px));
    max-height: calc(100vh - 80px);
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 20px 60px rgba(15, 23, 42, 0.22);
    display: flex;
    flex-direction: column;
}

.wizard-header,
.wizard-footer {
    padding: 18px 24px;
    border-bottom: 1px solid #edf0f5;
}

.wizard-footer {
    border-top: 1px solid #edf0f5;
    border-bottom: 0;
    display: flex;
    justify-content: space-between;
}

.wizard-body {
    padding: 20px 24px;
    overflow-y: auto;
}

.wizard-steps {
    display: flex;
    gap: 8px;
    margin-top: 16px;
}

.wizard-step {
    flex: 1;
    height: 34px;
    border-radius: 4px;
    background: #f3f6fb;
    color: #667085;
    display: flex;
    align-items: center;
    justify-content: center;
}

.wizard-step.active {
    background: #eaf2ff;
    color: #1f66ff;
    font-weight: 600;
}

.wizard-panel {
    display: none;
}

.wizard-panel.active {
    display: block;
}

.compact-list,
.asset-grid,
.preview-table {
    border: 1px solid #edf0f5;
    border-radius: 6px;
    overflow: hidden;
}

.compact-item,
.asset-item,
.preview-row {
    display: grid;
    gap: 12px;
    align-items: center;
    padding: 12px 14px;
    border-bottom: 1px solid #edf0f5;
}

.compact-item {
    grid-template-columns: 1fr 120px 60px;
}

.asset-item {
    grid-template-columns: 24px 1fr 160px;
}

.preview-row {
    grid-template-columns: 1.2fr 1fr 120px;
}

.compact-item:last-child,
.asset-item:last-child,
.preview-row:last-child {
    border-bottom: 0;
}

.form-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
}

.form-item label {
    display: block;
    margin-bottom: 6px;
    color: #344054;
    font-weight: 500;
}

.form-item input,
.form-item select {
    width: 100%;
    height: 34px;
    border: 1px solid #d7dce5;
    border-radius: 4px;
    padding: 0 10px;
}

.result-card {
    display: none;
    padding: 24px;
    border: 1px solid #c8ead0;
    border-radius: 6px;
    background: #f2fbf4;
}

.result-card.show {
    display: block;
}
```

- [ ] **Step 2: Add wizard markup**

Place modal markup before the closing `</body>`.

```html
<div class="modal-mask" id="wizardMask">
    <div class="wizard" role="dialog" aria-modal="true" aria-labelledby="wizardTitle">
        <div class="wizard-header">
            <h2 id="wizardTitle">批量应用策略模板</h2>
            <div class="wizard-steps">
                <div class="wizard-step active" data-step-label="1">确认模板</div>
                <div class="wizard-step" data-step-label="2">选择资产</div>
                <div class="wizard-step" data-step-label="3">公共配置</div>
            </div>
        </div>
        <div class="wizard-body">
            <section class="wizard-panel active" data-panel="1">
                <div class="compact-list" id="selectedTemplateList"></div>
            </section>
            <section class="wizard-panel" data-panel="2">
                <div class="asset-grid" id="assetList">
                    <label class="asset-item"><input type="checkbox" checked value="prod-web-01"><span>prod-web-01</span><span>生产环境</span></label>
                    <label class="asset-item"><input type="checkbox" checked value="prod-web-02"><span>prod-web-02</span><span>生产环境</span></label>
                    <label class="asset-item"><input type="checkbox" value="prod-db-01"><span>prod-db-01</span><span>生产环境</span></label>
                    <label class="asset-item"><input type="checkbox" value="test-host-01"><span>test-host-01</span><span>测试环境</span></label>
                </div>
            </section>
            <section class="wizard-panel" data-panel="3">
                <div class="form-grid">
                    <div class="form-item"><label>组织</label><select id="orgSelect"><option>Default</option><option>生产运维组</option></select></div>
                    <div class="form-item"><label>通知对象</label><input id="noticeTarget" value="主机负责人"></div>
                    <div class="form-item"><label>通知方式</label><select id="noticeChannel"><option>站内信 + 邮件</option><option>站内信</option><option>邮件</option></select></div>
                    <div class="form-item"><label>检测频率</label><select id="scheduleSelect"><option>每 1 分钟</option><option selected>每 5 分钟</option><option>每 10 分钟</option></select></div>
                    <div class="form-item"><label>策略名称前缀</label><input id="namePrefix" placeholder="例如：生产环境 - "></div>
                    <div class="form-item"><label>创建后启用</label><select id="enableSelect"><option selected>启用</option><option>暂不启用</option></select></div>
                </div>
                <h3>创建预览</h3>
                <div class="preview-table" id="strategyPreview"></div>
            </section>
            <section class="result-card" id="resultCard"></section>
        </div>
        <div class="wizard-footer">
            <button class="secondary-button" id="closeWizardButton" type="button">取消</button>
            <div class="batch-actions">
                <button class="secondary-button" id="prevStepButton" type="button">上一步</button>
                <button class="primary-button" id="nextStepButton" type="button">下一步</button>
            </div>
        </div>
    </div>
</div>
```

- [ ] **Step 3: Add wizard JavaScript**

Add step state, rendering, validation, and result behavior.

```javascript
let currentStep = 1;
const wizardMask = document.getElementById("wizardMask");
const selectedTemplateList = document.getElementById("selectedTemplateList");
const strategyPreview = document.getElementById("strategyPreview");
const resultCard = document.getElementById("resultCard");
const prevStepButton = document.getElementById("prevStepButton");
const nextStepButton = document.getElementById("nextStepButton");
const closeWizardButton = document.getElementById("closeWizardButton");
const namePrefix = document.getElementById("namePrefix");

function openWizard() {
    if (!selectedTemplates.size) return;
    currentStep = 1;
    resultCard.classList.remove("show");
    wizardMask.classList.add("show");
    renderSelectedTemplates();
    renderWizardStep();
}

function closeWizard() {
    wizardMask.classList.remove("show");
}

function renderWizardStep() {
    document.querySelectorAll(".wizard-step").forEach((step, index) => {
        step.classList.toggle("active", index + 1 === currentStep);
    });
    document.querySelectorAll(".wizard-panel").forEach((panel) => {
        panel.classList.toggle("active", Number(panel.dataset.panel) === currentStep);
    });
    prevStepButton.style.visibility = currentStep === 1 ? "hidden" : "visible";
    nextStepButton.textContent = currentStep === 3 ? "创建策略" : "下一步";
    if (currentStep === 3) renderStrategyPreview();
}

function renderSelectedTemplates() {
    selectedTemplateList.innerHTML = Array.from(selectedTemplates).map((title) => `
        <div class="compact-item" data-template="${title}">
            <div><strong>${title}</strong><div class="muted">使用模板默认阈值、算法和告警级别</div></div>
            <span>内置模板</span>
            <button class="link-button remove-template" type="button">移除</button>
        </div>
    `).join("");
    selectedTemplateList.querySelectorAll(".remove-template").forEach((button) => {
        button.addEventListener("click", () => {
            const title = button.closest(".compact-item").dataset.template;
            selectedTemplates.delete(title);
            cards.forEach((card) => {
                if (getCardTitle(card) === title) card.classList.remove("selected");
            });
            updateBatchBar();
            renderSelectedTemplates();
            if (!selectedTemplates.size) closeWizard();
        });
    });
}

function getSelectedAssetCount() {
    return document.querySelectorAll("#assetList input:checked").length;
}

function renderStrategyPreview() {
    const prefix = namePrefix.value || "";
    const assetCount = getSelectedAssetCount();
    strategyPreview.innerHTML = `
        <div class="preview-row"><strong>策略名称</strong><strong>资产范围</strong><strong>创建后状态</strong></div>
        ${Array.from(selectedTemplates).map((title) => `
            <div class="preview-row"><span>${prefix}${title}</span><span>${assetCount} 台主机</span><span>${document.getElementById("enableSelect").value}</span></div>
        `).join("")}
    `;
}

function submitBatch() {
    const total = selectedTemplates.size;
    document.querySelectorAll(".wizard-panel").forEach((panel) => panel.classList.remove("active"));
    resultCard.innerHTML = `<h3>创建完成</h3><p>成功创建 ${total} 条策略，每条策略覆盖 ${getSelectedAssetCount()} 台主机。</p>`;
    resultCard.classList.add("show");
    nextStepButton.style.display = "none";
    prevStepButton.style.display = "none";
}

prevStepButton.addEventListener("click", () => {
    currentStep = Math.max(1, currentStep - 1);
    renderWizardStep();
});

nextStepButton.addEventListener("click", () => {
    if (currentStep === 2 && getSelectedAssetCount() === 0) {
        alert("请至少选择 1 个监控资产");
        return;
    }
    if (currentStep === 3) {
        submitBatch();
        return;
    }
    currentStep += 1;
    renderWizardStep();
});

closeWizardButton.addEventListener("click", closeWizard);
namePrefix.addEventListener("input", renderStrategyPreview);
document.getElementById("enableSelect").addEventListener("change", renderStrategyPreview);
document.getElementById("assetList").addEventListener("change", renderStrategyPreview);
```

- [ ] **Step 4: Verify manually**

Open the prototype, select three templates, click `批量应用`, and step through the wizard.

Expected:
- Step 1 lists three templates.
- Removing one template updates the list and selected count.
- Step 2 requires at least one asset.
- Step 3 previews strategy count and names.
- Final submit shows success count equal to selected template count.

### Task 4: Browser Verification

**Files:**
- Verify: `spec/prototype/监控系统/事件/模版.html`

- [ ] **Step 1: Run static browser check**

Use Playwright to open the local file and verify key UI elements.

```javascript
const info = await page.evaluate(() => ({
  cardCount: document.querySelectorAll(".template-card").length,
  hasBatchBar: !!document.querySelector("#batchBar"),
  hasWizard: !!document.querySelector("#wizardMask"),
  activeSub: document.querySelector(".subnav .active")?.textContent.trim()
}));
```

Expected:

```json
{
  "cardCount": 12,
  "hasBatchBar": true,
  "hasWizard": true,
  "activeSub": "模板"
}
```

- [ ] **Step 2: Run interaction check**

Use Playwright to select two cards, open the wizard, move to the final step, and submit.

Expected:
- Selected count is `2`.
- Wizard opens.
- Preview has two strategy rows plus one header row.
- Result text contains `成功创建 2 条策略`.

- [ ] **Step 3: Commit prototype change**

Only commit the prototype file and this plan if not already committed.

```bash
git add docs/superpowers/plans/2026-06-09-monitor-template-batch-apply-prototype.md spec/prototype/监控系统/事件/模版.html
git commit -m "docs: prototype monitor template batch apply"
```
