import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEFAULT_CARD_LIST_MAX_ITEMS,
  formatCardListIndex,
  normalizeCardListAccentStyle,
  parseCardListItems,
  resolveCardListAccentPresentation,
  softAccentBackground,
  validateCardListPayload,
} from '../cardList';

const titleOnly = { titleField: 'title' };

test('empty payloads are valid empty', () => {
  for (const payload of [null, undefined, [], { items: [] }]) {
    const parsed = parseCardListItems(payload, titleOnly);
    assert.equal(parsed.status, 'empty');
    assert.equal(parsed.items.length, 0);
    assert.equal(validateCardListPayload(payload, titleOnly).isValid, true);
  }
});

test('array and items envelope both render valid primary records', () => {
  const fromArray = parseCardListItems(
    [{ title: 'A' }, { title: 'B' }],
    titleOnly,
  );
  const fromItems = parseCardListItems(
    { items: [{ title: 'A' }, { title: 'B' }] },
    titleOnly,
  );

  assert.equal(fromArray.status, 'ready');
  assert.deepEqual(
    fromArray.items.map((item) => item.primary),
    ['A', 'B'],
  );
  assert.deepEqual(
    fromItems.items.map((item) => item.primary),
    ['A', 'B'],
  );
});

test('mixed records skip non-records and missing primary then render remaining', () => {
  const parsed = parseCardListItems(
    [1, { title: 'A' }, {}, { title: 'B' }],
    titleOnly,
  );
  assert.equal(parsed.status, 'ready');
  assert.deepEqual(
    parsed.items.map((item) => item.primary),
    ['A', 'B'],
  );
});

test('non-empty payload with zero valid records is invalid', () => {
  assert.equal(validateCardListPayload([1, 2], titleOnly).isValid, false);
  assert.equal(validateCardListPayload([{}, {}], titleOnly).isValid, false);
  assert.equal(parseCardListItems([1, 2], titleOnly).status, 'invalid');
  assert.equal(parseCardListItems([{}, {}], titleOnly).status, 'invalid');
});

test('object scalar and graph payloads are invalid', () => {
  assert.equal(validateCardListPayload({ foo: 1 }, titleOnly).isValid, false);
  assert.equal(validateCardListPayload(0, titleOnly).isValid, false);
  assert.equal(validateCardListPayload(false, titleOnly).isValid, false);
  assert.equal(validateCardListPayload('', titleOnly).isValid, false);
  assert.equal(validateCardListPayload('x', titleOnly).isValid, false);
  assert.equal(
    validateCardListPayload({ data: [] }, titleOnly).isValid,
    false,
  );
  assert.equal(
    validateCardListPayload({ results: [] }, titleOnly).isValid,
    false,
  );
  assert.equal(
    validateCardListPayload({ nodes: [], edges: [] }, titleOnly).isValid,
    false,
  );
});

test('displayable scalars keep 0 and false and hide blank object array', () => {
  const parsed = parseCardListItems(
    [
      {
        title: 0,
        note: false,
        badge: '  ',
        extra: { nested: 1 },
        tags: ['a'],
      },
    ],
    {
      titleField: 'title',
      descriptionField: 'note',
      badgeField: 'badge',
      trailingPrimaryField: 'extra',
      trailingSecondaryField: 'tags',
    },
  );

  assert.equal(parsed.status, 'ready');
  assert.equal(parsed.items[0]?.primary, '0');
  assert.equal(parsed.items[0]?.secondary, 'false');
  assert.equal(parsed.items[0]?.badge, undefined);
  assert.equal(parsed.items[0]?.trailingPrimary, undefined);
  assert.equal(parsed.items[0]?.trailingSecondary, undefined);
});

test('whitespace primary is skipped and optional missing slots stay hidden', () => {
  const parsed = parseCardListItems(
    [
      { title: '   ', note: 'keep-me-out' },
      { title: 'Keep', note: null },
    ],
    {
      titleField: 'title',
      descriptionField: 'note',
    },
  );

  assert.equal(parsed.status, 'ready');
  assert.equal(parsed.items.length, 1);
  assert.equal(parsed.items[0]?.primary, 'Keep');
  assert.equal(parsed.items[0]?.secondary, undefined);
});

test('render safety cap keeps first 100 valid records in original order', () => {
  const rows = Array.from({ length: DEFAULT_CARD_LIST_MAX_ITEMS + 1 }, (_, index) => ({
    title: `R${index + 1}`,
  }));
  const parsed = parseCardListItems(rows, titleOnly);

  assert.equal(parsed.status, 'ready');
  assert.equal(parsed.total, DEFAULT_CARD_LIST_MAX_ITEMS + 1);
  assert.equal(parsed.truncated, true);
  assert.equal(parsed.items.length, DEFAULT_CARD_LIST_MAX_ITEMS);
  assert.equal(parsed.items[0]?.primary, 'R1');
  assert.equal(parsed.items[99]?.primary, 'R100');
});

test('index labels use zero-padded two digits until 100', () => {
  assert.equal(formatCardListIndex(1), '01');
  assert.equal(formatCardListIndex(9), '09');
  assert.equal(formatCardListIndex(99), '99');
  assert.equal(formatCardListIndex(100), '100');
});

test('index leading numbers rendered cards after skip and cap', () => {
  const rows = [
    1,
    { title: 'A' },
    {},
    { title: 'B' },
    ...Array.from({ length: DEFAULT_CARD_LIST_MAX_ITEMS }, (_, index) => ({
      title: `R${index + 3}`,
    })),
  ];
  const parsed = parseCardListItems(rows, {
    titleField: 'title',
    leading: { type: 'index' },
  });

  assert.equal(parsed.status, 'ready');
  assert.equal(parsed.truncated, true);
  assert.equal(parsed.items.length, DEFAULT_CARD_LIST_MAX_ITEMS);
  assert.equal(parsed.items[0]?.primary, 'A');
  assert.equal(parsed.items[0]?.leading, '01');
  assert.equal(parsed.items[1]?.primary, 'B');
  assert.equal(parsed.items[1]?.leading, '02');
  assert.equal(parsed.items[99]?.leading, '100');
});

test('normalizeCardListAccentStyle drops text display and empty mappings', () => {
  assert.equal(normalizeCardListAccentStyle(undefined), undefined);
  assert.equal(normalizeCardListAccentStyle({}), undefined);
  assert.equal(
    normalizeCardListAccentStyle({ displayType: 'text', valueMappings: [] }),
    undefined,
  );
  assert.deepEqual(
    normalizeCardListAccentStyle({
      displayType: 'textWithBackground',
      valueMappings: [
        {
          type: 'value',
          value: 'warn',
          result: { text: '警告', color: '#f0a000' },
        },
      ],
    }),
    {
      displayType: 'textWithBackground',
      valueMappings: [
        {
          type: 'value',
          value: 'warn',
          result: { text: '警告', color: '#f0a000' },
        },
      ],
    },
  );
  assert.deepEqual(
    normalizeCardListAccentStyle({
      displayType: 'colorBackground',
      valueMappings: [
        {
          type: 'value',
          value: 'P1',
          result: { text: '紧急', color: '#f00' },
        },
      ],
    }),
    {
      displayType: 'colorBackground',
      valueMappings: [
        {
          type: 'value',
          value: 'P1',
          result: { text: '紧急', color: '#f00' },
        },
      ],
    },
  );
});

test('softAccentBackground lightens hex into translucent rgba', () => {
  assert.equal(softAccentBackground('#f0a000'), 'rgba(240, 160, 0, 0.16)');
  assert.equal(softAccentBackground('#f00'), 'rgba(255, 0, 0, 0.16)');
});

test('resolveCardListAccentPresentation maps text, soft background and color dot', () => {
  const mappings = [
    {
      type: 'value' as const,
      value: 'P1',
      result: { text: '紧急', color: '#ff0000' },
    },
  ];

  assert.deepEqual(
    resolveCardListAccentPresentation('P1', { valueMappings: mappings }),
    {
      mode: 'text',
      displayText: '紧急',
      color: '#ff0000',
    },
  );

  assert.deepEqual(
    resolveCardListAccentPresentation('P1', {
      displayType: 'textWithBackground',
      valueMappings: mappings,
    }),
    {
      mode: 'textWithBackground',
      displayText: '紧急',
      color: '#ff0000',
      backgroundColor: 'rgba(255, 0, 0, 0.16)',
    },
  );

  assert.deepEqual(
    resolveCardListAccentPresentation('P1', {
      displayType: 'colorBackground',
      valueMappings: mappings,
    }),
    {
      mode: 'colorDot',
      color: '#ff0000',
      tooltipText: '紧急',
    },
  );

  assert.deepEqual(resolveCardListAccentPresentation('01', undefined), {
    mode: 'plain',
    displayText: '01',
  });

  assert.deepEqual(
    resolveCardListAccentPresentation('P2', {
      displayType: 'colorBackground',
      valueMappings: mappings,
    }),
    { mode: 'plain', displayText: 'P2' },
  );
});

test('text-only mapping changes label without coloring', () => {
  assert.deepEqual(
    resolveCardListAccentPresentation('P1', {
      valueMappings: [
        { type: 'value', value: 'P1', result: { text: '紧急' } },
      ],
    }),
    { mode: 'plain', displayText: '紧急' },
  );
});
