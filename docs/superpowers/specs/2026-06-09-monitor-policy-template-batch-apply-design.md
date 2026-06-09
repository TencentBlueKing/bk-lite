# Monitor Policy Template Batch Apply Design

## Background

The current monitor event template page supports only one template at a time. A user selects a template card, enters the strategy detail page, selects assets, confirms configuration, and creates one strategy. This makes basic monitor onboarding slow when users need several standard policies for the same asset scope, such as CPU, memory, disk, load, and network traffic.

The target experience is inspired by Datadog-style batch monitor creation: select multiple templates, select monitor assets once, confirm shared configuration, and create multiple monitor strategies together.

## Goals

- Allow users to select multiple policy templates from the monitor event template page.
- Let users choose target assets once and apply all selected templates to those assets.
- Create strategies by template count, not by asset count. For example, selecting 5 templates and 20 hosts creates 5 strategies, each covering the same 20 hosts.
- Keep batch creation easy to understand by only exposing lightweight shared settings.
- Keep threshold, algorithm, and alert level configuration from each template unchanged during the batch flow.

## Non-Goals

- Do not introduce template packages in this iteration.
- Do not support per-template threshold or alert level editing in the batch flow.
- Do not generate one strategy per asset.
- Do not redesign the existing single-template creation detail page.

## Current Flow

The current page at `web/src/app/monitor/(pages)/event/template/page.tsx` fetches templates by monitor object through `/monitor/api/monitor_policy/template/`. A card click stores a single template in `sessionStorage.strategyInfo` and navigates to `/monitor/event/strategy/detail?type=builtIn`.

The strategy detail page reads that single template and creates one policy through `/monitor/api/monitor_policy/`.

## Proposed Flow

### 1. Template Selection

The event template page becomes a grouped multi-select surface:

- Templates are grouped by integration template, such as `Host (Telegraf)` and `Host Remote`.
- Each group shows its template count, selected count, and a `select group` action.
- Each template card has a checkbox.
- Clicking a card toggles selection.
- Each template card shows the alert template name, metric, and source integration template, for example `Host (Telegraf) - Memory Usage`.
- The page shows a Datadog-style floating selection tray after users select templates. The tray contains selected count, a few selected-template tags, `clear`, and `batch apply`.
- The page may keep a lightweight hover-only single-template action for the existing one-template flow.

### 2. Batch Apply Wizard

After clicking `批量应用`, users enter a 3-step wizard.

#### Step 1: Confirm Templates

Show selected templates grouped by integration template, with template name, metric, and source integration template. Users can remove templates from the batch. Thresholds, algorithms, and alert levels are displayed only as template defaults if needed; they are not editable in this flow.

#### Step 2: Select Assets

Users select assets under the current monitor object, such as host assets. The selected assets are shared by every strategy created from the selected templates.

The asset selector is a table with these columns:

- Asset name.
- Organization.
- Collection template.

#### Step 3: Shared Configuration

Users configure lightweight settings shared by all generated strategies:

- Organization.
- Detection frequency.
- Detection period.
- Notification enabled switch.
- Notification channel cards.
- Notifier selector. If selected channels are all NATS-style channels, notifier can be skipped.
- Whether strategies are enabled after creation.
- Strategy name rule or prefix.

Alert level, threshold, and algorithm are intentionally excluded because they are complex template-specific settings.

### 3. Strategy Generation

The system creates one strategy per selected template.

Example:

- Selected templates: CPU, memory, disk, load, network in.
- Selected assets: 20 hosts.
- Created strategies: 5 strategies.
- Each strategy targets the same 20 hosts.

Template defaults provide metric, threshold, algorithm, alert level, and alert name baseline. Shared wizard settings override only the lightweight fields selected in step 3.

## Naming

The default strategy name should use the template name. Users can optionally provide a shared prefix.

Examples:

- Without prefix: `CPU使用率过高`, `内存使用率过高`.
- With prefix `生产环境 - `: `生产环境 - CPU使用率过高`, `生产环境 - 内存使用率过高`.

The final confirmation step should preview the strategy names before creation.

## Result Feedback

After submission, show a result summary:

- Successfully created count.
- Failed count.
- Per-template failure reason, such as missing metric, incompatible asset scope, or duplicated strategy name.

After success, users can go to the strategy list. The list should ideally filter or highlight the strategies created in this batch.

## UX Principles

- The template page is for choosing what to apply.
- The wizard is for choosing where to apply and confirming shared settings.
- Complex template tuning stays in the single-strategy edit flow.
- Batch creation should feel predictable: users must know how many strategies will be created before submitting.

## Implementation Notes

- Frontend can initially keep batch creation client-orchestrated by calling the existing create policy endpoint once per selected template.
- A backend batch endpoint can be added later if atomic behavior, partial retry, or better result reporting becomes necessary.
- The UI should preserve the current monitor object tree and template filtering behavior.
- The batch wizard should avoid storing large payloads in `sessionStorage` if a route-based wizard is added; a local state store or compact template identifiers are preferable.

## Open Decisions

- Whether batch creation should be all-or-nothing or allow partial success.
- Whether duplicate strategy names should block creation or auto-suffix names.
- Whether the result page should offer retry for failed templates.
