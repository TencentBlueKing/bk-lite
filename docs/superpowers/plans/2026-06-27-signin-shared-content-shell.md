# Signin Shared Content Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `SigninClient` render one shared authentication content design in both page and modal containers, while keeping page and modal titles owned by their outer shells.

**Architecture:** Keep `SigninClient` as the authentication state and flow orchestrator. Inside `SigninClient`, split the page-mode shell from the shared authentication content area so both the login page and session-expired modal consume the same content structure, while `auth.tsx` continues to own the modal heading/description and `page.tsx` remains a thin server entry.

**Tech Stack:** Next.js 16, React 19, TypeScript, Ant Design, existing login-auth hooks and auth context

## Execution Constraints

- The primary objective is to complete the shared signin content-shell refinement end-to-end for both page and modal containers.
- Prefer lightweight, directly relevant validation while implementing; reserve full verification for the final verification task unless a risky change justifies earlier deeper checks.
- Do not force through ambiguous issues. If component ownership, shell/content boundaries, binding ordering behavior, or responsive layout direction becomes unclear, stop and align with the user before continuing.
- Follow existing repository code style and implementation patterns.
- Keep changes tightly scoped to the signin/auth UI refinement; avoid unrelated refactors, opportunistic cleanup, or broad restructuring outside the affected auth files.
- Treat task completion as behaviorally meeting the confirmed end-state, not merely landing partial code or passing isolated interim checks.
- Prefer no temporary compatibility layer unless explicitly required.

## Global Constraints

- Preserve the existing auth flow state machine in `SigninClient.tsx`; do not fork login logic for page vs modal.
- `auth.tsx` must keep ownership of the session-expired modal title and description.
- The login page shell inside `web/src/app/(core)/auth/signin/SigninClient.tsx` must keep ownership of the `Sign In` title and description region for page mode.
- In modal mode, `SigninClient` must only render the area below the modal heading/description.
- The shared content design must support the confirmed structure: upper content area + lower login-method list.
- The lower login-method list must use the confirmed `L2` style: icon above label, compact wrapping layout, selected state only on icon border and label color, no helper descriptions.
- Builtin login renders the username/password form in the content area.
- External login renders one unified minimal structure in the content area: fixed session-expired semantics handled by shell, body copy + primary button `Use {binding.name} to sign in` + lightweight return hint.
- Keep diffs focused to auth/signin files and the supporting story used to validate this UI.

---

## File Structure

- Modify: `web/src/app/(core)/auth/signin/SigninClient.tsx`
  - Keep auth flow orchestration.
  - Split internal rendering into page shell and shared auth content.
  - Route the shared content into focused subcomponents.
- Create: `web/src/app/(core)/auth/signin/login-auth/SigninContentShell.tsx`
  - Shared wrapper for the content area and login-method list.
  - Accepts mode-sensitive spacing only, not semantic heading ownership.
- Create: `web/src/app/(core)/auth/signin/login-auth/BuiltinSigninContent.tsx`
  - Username/password form content only.
- Modify: `web/src/app/(core)/auth/signin/login-auth/LoginAuthBindingContent.tsx`
  - Convert external binding content to the confirmed unified minimal layout.
- Modify: `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx`
  - Replace current large card grid with the confirmed `L2` compact icon-over-label method list.
- Modify: `web/src/context/auth.tsx`
  - Keep current modal shell ownership but adjust container sizing/padding only if needed for the shared content shell.
- Keep unchanged unless needed: `web/src/app/(core)/auth/signin/page.tsx`
  - Preserve the current thin server-entry responsibility.
- Modify: `web/src/stories/session-expired-modal-directions.stories.tsx`
  - Convert from design exploration artifact into final preview-aligned story, or replace with a component-backed story if practical in the same task.
- Create or modify: `web/src/stories/...signin...stories.tsx`
  - Add a real preview story for page and modal container states if the current design-only story is insufficient.

## Task 1: Separate The Internal Page Shell From Shared Auth Content

**Files:**
- Modify: `web/src/app/(core)/auth/signin/SigninClient.tsx`
- Modify: `web/src/context/auth.tsx`

**Interfaces:**
- Consumes: existing `SigninClientProps`, `mode`, `onAuthenticated`
- Produces: `SigninClient` renders page shell + shared content in `page` mode, and only shared content in `modal` mode

- [ ] **Step 1: Document the render boundary inside `SigninClient.tsx`**

Add a short implementation note near the content render block:

```tsx
// SigninClient owns the shared authentication content area.
// In page mode it wraps that content with the page shell; in modal mode
// the modal shell above is rendered by auth.tsx.
```

- [ ] **Step 2: Extract shared auth content from the page shell in `SigninClient.tsx`**

Keep the page-only heading outside the shared content tree and make `content` represent only the reusable auth area:

```tsx
const content = (
  <div className={`w-full ${isModalMode ? '' : 'max-w-md'}`} style={isModalMode ? { maxWidth: 388 } : undefined}>
    {error && ...}
    {formError && ...}
    {validationInlineError && ...}
    ...
  </div>
);
```

- [ ] **Step 3: Preserve the page heading in the page-mode shell inside `SigninClient.tsx`**

Keep the page shell return branch, but make it wrap a page-mode heading block and the extracted shared content:

```tsx
return (
  <div className="flex w-[calc(100%+2rem)] h-screen -m-4">
    <div className="w-3/5 hidden md:block ..." />
    <div className="w-full h-full md:w-2/5 flex items-center justify-center p-8 bg-(--bg-color-1) overflow-y-auto">
      <div className="w-full max-w-md">
        <div className="text-center mb-10">
          <div className="flex justify-center mb-6">
            <img src={logoUrl} alt="Logo" className="h-14 w-auto object-contain" />
          </div>
          <h2 className="text-3xl font-bold text-(--color-text-1)">Sign In</h2>
          <p className="text-(--color-text-3) mt-2">Enter your credentials to continue</p>
        </div>
        <PageHeading />
        {sharedContent}
      </div>
    </div>
  </div>
);
```

- [ ] **Step 4: Preserve modal heading ownership in `auth.tsx`**

Keep this block as the modal shell heading owner:

```tsx
<div className="mb-6">
  <div className="mx-auto max-w-md text-center">
    <div className="text-[16px] font-semibold leading-none text-(--color-text-1)">
      {t('common.sessionExpiredTitle')}
    </div>
    <div className="mx-auto mt-2 max-w-sm text-[12px] leading-5 text-(--color-text-2)">
      {t('common.sessionExpiredDescription')}
    </div>
  </div>
</div>
```

- [ ] **Step 5: Verify render ownership manually**

Run: `cd web && pnpm exec storybook dev -p 6006`

Expected:
- page container still shows `Sign In` heading above the auth content
- modal container still shows session-expired heading above the auth content
- `SigninClient` no longer mixes the page heading into the shared content tree

## Task 2: Create One Shared Auth Content Shell

**Files:**
- Create: `web/src/app/(core)/auth/signin/login-auth/SigninContentShell.tsx`
- Create: `web/src/app/(core)/auth/signin/login-auth/BuiltinSigninContent.tsx`
- Modify: `web/src/app/(core)/auth/signin/SigninClient.tsx`

**Interfaces:**
- Consumes:
  - builtin form state from `SigninClient`
  - selected binding state from `useLoginAuthValidation`
  - `mode: 'page' | 'modal'`
- Produces:
  - `SigninContentShell(props)`
  - `BuiltinSigninContent(props)`

- [ ] **Step 1: Create `BuiltinSigninContent.tsx`**

Use the current form markup from `renderLoginForm` and move it behind props:

```tsx
interface BuiltinSigninContentProps {
  mode: 'page' | 'modal';
  username: string;
  password: string;
  isLoading: boolean;
  onUsernameChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: React.FormEvent) => void;
}
```

- [ ] **Step 2: Create `SigninContentShell.tsx`**

Define one wrapper that renders content above and method list below:

```tsx
interface SigninContentShellProps {
  mode: 'page' | 'modal';
  mainContent: React.ReactNode;
  methodsContent?: React.ReactNode;
}

export default function SigninContentShell({
  mode,
  mainContent,
  methodsContent,
}: SigninContentShellProps) {
  return (
    <div className={`w-full ${mode === 'modal' ? '' : 'max-w-md'}`}>
      <div>{mainContent}</div>
      {methodsContent ? <div className={mode === 'modal' ? 'mt-4' : 'mt-5'}>{methodsContent}</div> : null}
    </div>
  );
}
```

- [ ] **Step 3: Replace inline render helpers in `SigninClient.tsx`**

Swap `renderLoginForm()` usage with:

```tsx
<BuiltinSigninContent
  mode={mode}
  username={username}
  password={password}
  isLoading={isLoading}
  onUsernameChange={setUsername}
  onPasswordChange={setPassword}
  onSubmit={handleLoginSubmit}
/>
```

- [ ] **Step 4: Render through `SigninContentShell`**

Refactor the login-step render branch to:

```tsx
<SigninContentShell
  mode={mode}
  mainContent={showBuiltinLoginForm ? builtinContent : bindingContent}
  methodsContent={showBindingsSelector ? bindingsSelector : null}
/>
```

- [ ] **Step 5: Verify no auth flow behavior changed**

Run: `cd web && pnpm exec tsx -e "console.log('shell refactor smoke')"`

Expected: command exits `0`

Then manually verify Storybook / local page:
- builtin binding still submits through existing form logic
- external binding still routes through `startSelectedBindingLogin`

## Task 3: Restyle External Binding Content To The Confirmed Minimal Layout

**Files:**
- Modify: `web/src/app/(core)/auth/signin/login-auth/LoginAuthBindingContent.tsx`

**Interfaces:**
- Consumes:
  - `selectedBinding`
  - `onContinueThirdParty`
  - `viewState`
- Produces:
  - one unified external-content layout for ready state

- [ ] **Step 1: Keep loading/error/waiting states behaviorally intact**

Do not rewrite the state machine branches; only restyle them to fit the lighter shared shell if needed.

- [ ] **Step 2: Replace ready-state external content**

Change the ready-state branch to a minimal structure:

```tsx
return (
  <div className="rounded-[16px] border border-[#E5EBF3] bg-white px-5 py-5 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
    <div className={`${isModalMode ? 'text-[24px]' : 'text-[28px]'} font-semibold leading-tight text-(--color-text-1)`}>
      {isModalMode ? '登录已过期' : 'Sign In'}
    </div>
    <p className={`mt-2 text-(--color-text-3) ${isModalMode ? 'text-[13px] leading-6' : 'text-sm leading-6'}`}>
      {`You are using ${selectedBinding.name} to continue sign-in. After authentication, you will return to the current page.`}
    </p>
    <button
      type="button"
      onClick={onContinueThirdParty}
      className={`mt-5 inline-flex w-full items-center justify-center rounded-[10px] bg-[#246BFD] text-white transition-colors hover:bg-[#1F5DE0] ${isModalMode ? 'h-11 text-[14px] font-medium' : 'h-11 text-sm font-medium'}`}
    >
      {`Use ${selectedBinding.name} to sign in`}
    </button>
    <div className="mt-3 rounded-[10px] border border-[#D7E0EA] bg-[#F8FAFC] px-3 py-2 text-[12px] leading-5 text-(--color-text-3)">
      You will return to your current task after authentication completes.
    </div>
  </div>
);
```

- [ ] **Step 3: Remove decorative provider hero blocks**

Delete the current large centered icon tile and separate provider title block from the ready state.

- [ ] **Step 4: Verify wording is shell-safe**

Ensure modal mode does not reintroduce page shell copy and page mode does not own session-expired semantics outside the content block’s body text.

## Task 4: Restyle The Method Selector To Confirmed L2

**Files:**
- Modify: `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx`

**Interfaces:**
- Consumes:
  - `bindings`
  - `selectedBindingId`
  - `isSelectionLocked`
  - `onSelectBinding`
- Produces:
  - compact wrapping icon-over-label selector

- [ ] **Step 1: Replace the current 104px card grid**

Use a smaller wrapping selector container:

```tsx
<div className="flex flex-wrap gap-3">
```

- [ ] **Step 2: Render each binding as an `L2` item**

Target structure:

```tsx
<button
  key={binding.id}
  type="button"
  onClick={() => onSelectBinding(binding.id)}
  disabled={isDisabled}
  aria-pressed={isActive}
  className="flex min-w-[68px] flex-col items-center gap-1.5 bg-transparent p-0 text-center"
>
  <span className={`flex h-10 w-10 items-center justify-center rounded-[12px] ${isActive ? 'border border-[#BFD5FF] bg-[#E8F0FF]' : 'border border-transparent bg-[#F4F7FB]'}`}>
    ...
  </span>
  <span className={`max-w-[64px] text-[11px] leading-[1.25] ${isActive ? 'text-[#1E4FD6]' : 'text-(--color-text-2)'}`}>
    {binding.name}
  </span>
</button>
```

- [ ] **Step 3: Keep wrapping behavior**

Do not truncate to a single row. Long labels should wrap within the small width instead of stretching the row.

- [ ] **Step 4: Remove helper descriptions from list items**

Only icon and label remain.

## Task 5: Replace The Design Exploration Story With A Final Preview Story

**Files:**
- Modify: `web/src/stories/session-expired-modal-directions.stories.tsx`
- Optionally create: `web/src/stories/signin-client-auth-shell.stories.tsx`

**Interfaces:**
- Consumes:
  - final visual decisions from Tasks 1-4
- Produces:
  - one preview story for modal shell
  - one preview story for page shell if feasible

- [ ] **Step 1: Stop using comparative exploration copy**

Replace “compare directions” framing with final preview wording.

- [ ] **Step 2: Show builtin-selected state**

Include a story state where the first binding is builtin and the main content is the username/password form.

- [ ] **Step 3: Show external-selected state**

Include a story state where an external binding is selected and the main content uses the unified “description + primary button” model.

- [ ] **Step 4: Keep page and modal containers visually separate**

If two stories are easier than one, prefer:

```tsx
export const ModalPreview = ...
export const PagePreview = ...
```

## Task 6: Verify The Shared Shell In Real Constraints

**Files:**
- Test: `web/src/app/(core)/auth/signin/SigninClient.tsx`
- Test: `web/src/context/auth.tsx`
- Test: `web/src/app/(core)/auth/signin/login-auth/LoginAuthBindingContent.tsx`
- Test: `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx`

**Interfaces:**
- Consumes: final implementation from Tasks 1-5
- Produces: validation evidence that shared shell works in both containers

- [ ] **Step 1: Run lint-sensitive type baseline**

Run: `cd web && pnpm type-check`

Expected: exits `0`

- [ ] **Step 2: Open final Storybook preview**

Run: `cd web && pnpm exec storybook dev -p 6006`

Expected:
- page shell heading remains outside the shared auth content
- modal shell heading remains outside the shared auth content
- builtin and external selected states both fit inside the modal-width content area

- [ ] **Step 3: Manual responsive check**

Verify at minimum:
- modal-width content (`~388px`) does not overflow
- method selector wraps cleanly
- page shell right column still centers content correctly

## Self-Review

- Spec coverage: this plan covers the confirmed shell ownership split, shared content shell, builtin/external content split, `L2` method selector, and story verification.
- Placeholder scan: no `TODO`/`TBD` placeholders remain.
- Type consistency: `SigninContentShell`, `BuiltinSigninContent`, existing `LoginAuthBindingContent`, and `LoginAuthValidationPanel` responsibilities are explicit and consistent with `SigninClient` orchestration.

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-27-signin-shared-content-shell.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
