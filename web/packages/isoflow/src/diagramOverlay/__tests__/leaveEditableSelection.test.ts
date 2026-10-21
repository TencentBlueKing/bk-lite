// @ts-nocheck
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: 'http://localhost/'
});

const browserWindow = dom.window;
globalThis.window = browserWindow as unknown as Window & typeof globalThis;
globalThis.document = browserWindow.document;
globalThis.HTMLElement = browserWindow.HTMLElement;
globalThis.SVGElement = browserWindow.SVGElement;
globalThis.Node = browserWindow.Node;
globalThis.getComputedStyle = browserWindow.getComputedStyle.bind(browserWindow);
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

for (const key of Object.getOwnPropertyNames(browserWindow)) {
  if (key in globalThis) continue;
  try {
    (globalThis as Record<string, unknown>)[key] = browserWindow[key as keyof typeof browserWindow];
  } catch {
    // Some window accessors are not installable on globalThis.
  }
}

const main = async () => {
const React = (await import('react')).default;
const { act } = await import('react');
const { createRoot } = await import('react-dom/client');
const { UiStateProvider, useUiStateStore } = await import('src/stores/uiStateStore');
const {
  DiagramOverlayProvider,
  useDiagramCallbacksRef,
  useDiagramVisual
} = await import('src/diagramOverlay/context');
const { emitItemSelect } = await import('src/diagramOverlay/callbacks');

type Mode = 'EDITABLE' | 'EXPLORABLE_READONLY';
type Hit = { type: 'ITEM' | 'RECTANGLE' | 'CONNECTOR' | 'TEXTBOX'; id: string };

const snapshot: {
  itemControls: Hit | null;
  modeType: string;
  highlightedItemId?: string;
} = {
  itemControls: null,
  modeType: ''
};

const Probe = () => {
  snapshot.itemControls = useUiStateStore((state) => state.itemControls) as Hit | null;
  snapshot.modeType = useUiStateStore((state) => state.mode.type);
  snapshot.highlightedItemId = useDiagramVisual().highlightedItemId;
  return null;
};

const BootSelection = ({ hit }: { hit: Hit | null }) => {
  const actions = useUiStateStore((state) => state.actions);
  const callbacksRef = useDiagramCallbacksRef();
  const started = React.useRef(false);

  React.useEffect(() => {
    if (started.current || !hit) return;
    if (callbacksRef.current.editorMode !== 'EDITABLE') return;
    started.current = true;
    actions.setItemControls(hit);
    if (hit.type === 'TEXTBOX') return;
    emitItemSelect(callbacksRef, { type: hit.type, id: hit.id });
  });

  return null;
};

const ModeSync = ({ mode }: { mode: Mode }) => {
  const actions = useUiStateStore((state) => state.actions);
  React.useEffect(() => {
    actions.setEditorMode(mode);
  }, [actions, mode]);
  return null;
};

const mount = () => {
  const host = document.createElement('div');
  document.body.appendChild(host);
  return createRoot(host);
};

const flush = async () => {
  await act(async () => {
    await new Promise((resolve) => {
      setTimeout(resolve, 0);
    });
  });
};

const renderTree = async (
  root: ReturnType<typeof createRoot>,
  mode: Mode,
  hit: Hit | null,
  onItemSelect: (item: { type: string; id: string } | null) => void,
  highlightedItemId: string,
  extra?: React.ReactNode
) => {
  await act(() => {
    root.render(
      React.createElement(
        UiStateProvider,
        null,
        React.createElement(ModeSync, { mode }),
        React.createElement(
          DiagramOverlayProvider,
          { editorMode: mode, onItemSelect, highlightedItemId },
          React.createElement(BootSelection, { hit }),
          extra ?? null,
          React.createElement(Probe)
        )
      )
    );
  });
  await flush();
};

const keyOf = (item: { type: string; id: string } | null) => {
  return item ? `${item.type}:${item.id}` : 'null';
};

for (const hit of [
  { type: 'ITEM' as const, id: 'node-db' },
  { type: 'RECTANGLE' as const, id: 'region-core' },
  { type: 'CONNECTOR' as const, id: 'link-1' }
]) {
  const calls: string[] = [];
  const root = mount();
  await renderTree(root, 'EDITABLE', hit, (item) => calls.push(keyOf(item)), 'keep-highlight');
  assert.deepEqual(calls, [`${hit.type}:${hit.id}`]);
  assert.deepEqual(snapshot.itemControls, hit);
  assert.equal(snapshot.modeType, 'CURSOR');
  assert.equal(snapshot.highlightedItemId, 'keep-highlight');

  await renderTree(
    root,
    'EXPLORABLE_READONLY',
    hit,
    (item) => calls.push(keyOf(item)),
    'keep-highlight'
  );
  assert.deepEqual(calls, [`${hit.type}:${hit.id}`, 'null']);
  assert.equal(snapshot.itemControls, null);
  assert.equal(snapshot.modeType, 'PAN');
  assert.equal(snapshot.highlightedItemId, 'keep-highlight');
  await act(() => {
    root.unmount();
  });
}

{
  const calls: string[] = [];
  const root = mount();
  await renderTree(root, 'EDITABLE', null, (item) => calls.push(keyOf(item)), 'region-view');
  await renderTree(root, 'EXPLORABLE_READONLY', null, (item) => calls.push(keyOf(item)), 'region-view');
  assert.deepEqual(calls, []);
  assert.equal(snapshot.itemControls, null);
  assert.equal(snapshot.highlightedItemId, 'region-view');
  await act(() => {
    root.unmount();
  });
}

{
  const calls: string[] = [];
  const root = mount();
  const hit = { type: 'RECTANGLE' as const, id: 'region-core' };
  await renderTree(root, 'EDITABLE', hit, (item) => calls.push(keyOf(item)), 'stay');

  const ClearSelection = () => {
    const actions = useUiStateStore((state) => state.actions);
    const cleared = React.useRef(false);
    React.useEffect(() => {
      if (cleared.current) return;
      cleared.current = true;
      actions.setItemControls(null);
    });
    return null;
  };

  await renderTree(
    root,
    'EDITABLE',
    hit,
    (item) => calls.push(keyOf(item)),
    'stay',
    React.createElement(ClearSelection)
  );
  assert.deepEqual(calls, ['RECTANGLE:region-core', 'null']);
  assert.equal(snapshot.itemControls, null);
  assert.equal(snapshot.modeType, 'CURSOR');
  assert.equal(snapshot.highlightedItemId, 'stay');

  await renderTree(root, 'EXPLORABLE_READONLY', hit, (item) => calls.push(keyOf(item)), 'stay');
  assert.deepEqual(calls, ['RECTANGLE:region-core', 'null']);
  assert.equal(snapshot.highlightedItemId, 'stay');
  await act(() => {
    root.unmount();
  });
}

{
  const calls: string[] = [];
  const root = mount();
  const hit = { type: 'TEXTBOX' as const, id: 'caption-1' };
  await renderTree(root, 'EDITABLE', hit, (item) => calls.push(keyOf(item)), 'text-view');
  assert.deepEqual(snapshot.itemControls, hit);
  assert.deepEqual(calls, []);
  await renderTree(root, 'EXPLORABLE_READONLY', hit, (item) => calls.push(keyOf(item)), 'text-view');
  assert.equal(snapshot.itemControls, null);
  assert.equal(snapshot.modeType, 'PAN');
  assert.deepEqual(calls, []);
  assert.equal(snapshot.highlightedItemId, 'text-view');
  await act(() => {
    root.unmount();
  });
}

console.log('leaveEditableSelection ok');
};

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
