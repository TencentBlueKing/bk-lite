import assert from 'node:assert/strict';
import test from 'node:test';
import {
  SINGLE_VALUE_ICON_FONT_RATIO,
  SINGLE_VALUE_ICON_GAP_RATIO,
  ensureSingleValueIconFileType,
  isSingleValueIconDataUrl,
  persistSingleValueStyle,
  readSingleValueStyle,
  resolveSingleValueIconBox,
  resolveSingleValueIconSrc,
  validateSingleValueIconFile,
} from '../singleValueStyle';

test('missing style keeps the legacy defaults', () => {
  const style = readSingleValueStyle(undefined);
  assert.equal(style.showIcon, false);
  assert.equal(style.iconSource, undefined);
  assert.equal(style.iconPosition, 'left');
  assert.equal(style.iconSize, 'medium');
  assert.equal(style.align, undefined);
  assert.equal(persistSingleValueStyle(undefined), undefined);
  assert.equal(
    persistSingleValueStyle({ showIcon: false, iconPosition: 'left', iconSize: 'medium' }),
    undefined,
  );
  assert.deepEqual(
    persistSingleValueStyle({ showIcon: false, align: 'left', iconPosition: 'left' }),
    { align: 'left' },
  );
});

test('persist keeps an enabled icon and drops invalid images', () => {
  const stored = persistSingleValueStyle({
    showIcon: true,
    iconSource: 'upload',
    iconImage: 'data:image/png;base64,abc',
    iconPosition: 'right',
    iconSize: 'large',
    align: 'center',
  });
  assert.deepEqual(stored, {
    showIcon: true,
    iconSource: 'upload',
    iconImage: 'data:image/png;base64,abc',
    iconPosition: 'right',
    iconSize: 'large',
    align: 'center',
  });
  assert.equal(
    persistSingleValueStyle({
      showIcon: true,
      iconSource: 'upload',
      iconImage: 'https://example.com/a.png',
    })?.iconImage,
    undefined,
  );
});

test('alignment is stored only when the draft has a value', () => {
  assert.equal(persistSingleValueStyle({ showIcon: false })?.align, undefined);
  assert.equal(persistSingleValueStyle({ align: 'left' })?.align, 'left');
  assert.equal(persistSingleValueStyle({ align: 'center' })?.align, 'center');
  assert.equal(persistSingleValueStyle({ align: 'right' })?.align, 'right');
});

test('persist keeps only the active icon source', () => {
  const image = 'data:image/png;base64,abc';
  assert.equal(readSingleValueStyle({ showIcon: true }).iconSource, 'builtin');
  assert.equal(
    readSingleValueStyle({ showIcon: true, iconKey: 'cc-host' }).iconSource,
    'builtin',
  );
  assert.deepEqual(
    persistSingleValueStyle({
      showIcon: true,
      iconKey: 'cc-host',
      iconImage: image,
    }),
    { showIcon: true },
  );
  assert.deepEqual(
    persistSingleValueStyle({
      showIcon: true,
      iconSource: 'builtin',
      iconKey: 'cc-host',
      iconImage: image,
    }),
    { showIcon: true, iconKey: 'cc-host' },
  );
  assert.deepEqual(
    persistSingleValueStyle({
      showIcon: true,
      iconSource: 'upload',
      iconKey: 'cc-host',
      iconImage: image,
    }),
    { showIcon: true, iconSource: 'upload', iconImage: image },
  );
  const kept = readSingleValueStyle({
    showIcon: true,
    iconSource: 'upload',
    iconKey: 'cc-host',
    iconImage: image,
  });
  assert.equal(kept.iconSource, 'upload');
  assert.equal(kept.iconKey, 'cc-host');
  assert.equal(kept.iconImage, image);
});

test('icon file accepts png jpg webp svg within 100KB', () => {
  assert.equal(validateSingleValueIconFile({ name: 'a.png', type: 'image/png', size: 100 }), null);
  assert.equal(validateSingleValueIconFile({ name: 'a.jpg', type: 'image/jpeg', size: 100 }), null);
  assert.equal(validateSingleValueIconFile({ name: 'a.webp', type: '', size: 100 }), null);
  assert.equal(validateSingleValueIconFile({ name: 'a.svg', type: 'image/svg+xml', size: 100 }), null);
  assert.equal(validateSingleValueIconFile({ name: 'a.gif', type: 'image/gif', size: 100 }), 'type');
  assert.equal(validateSingleValueIconFile({ name: 'a.svg', type: 'text/html', size: 100 }), 'type');
  assert.equal(
    validateSingleValueIconFile({ name: 'a.png', type: 'image/png', size: 100 * 1024 + 1 }),
    'size',
  );
  assert.equal(isSingleValueIconDataUrl('data:image/webp;base64,xx'), true);
  assert.equal(isSingleValueIconDataUrl('data:text/plain,xx'), false);
  assert.equal(isSingleValueIconDataUrl('data:;base64,xx'), false);

  const emptyType = new File(['icon'], 'mark.webp', { type: '' });
  const readable = ensureSingleValueIconFileType(emptyType);
  assert.equal(emptyType.type, '');
  assert.equal(readable.type, 'image/webp');
  assert.equal(readable.name, 'mark.webp');
  assert.equal(
    ensureSingleValueIconFileType(new File(['icon'], 'mark.png', { type: 'image/png' })).type,
    'image/png',
  );
});

test('builtin icon needs a key and upload icon needs a data url', () => {
  const resolveBuiltin = (iconKey: string) => `/assets/${iconKey}.svg`;
  assert.equal(
    resolveSingleValueIconSrc(readSingleValueStyle({ showIcon: true }), resolveBuiltin),
    null,
  );
  assert.equal(
    resolveSingleValueIconSrc(
      readSingleValueStyle({ showIcon: true, iconKey: 'cc-host' }),
      resolveBuiltin,
    ),
    '/assets/cc-host.svg',
  );
  assert.equal(
    resolveSingleValueIconSrc(
      readSingleValueStyle({
        showIcon: true,
        iconSource: 'upload',
        iconImage: 'data:image/svg+xml;base64,abc',
      }),
      resolveBuiltin,
    ),
    'data:image/svg+xml;base64,abc',
  );
  assert.equal(
    resolveSingleValueIconSrc(
      readSingleValueStyle({ showIcon: false, iconKey: 'cc-host' }),
      resolveBuiltin,
    ),
    null,
  );
});

test('icon tracks the value font, then shrinks and hides when the row is narrow', () => {
  const fontSize = 40;
  const textWidth = 120;
  const medium = SINGLE_VALUE_ICON_FONT_RATIO.medium * fontSize;
  assert.deepEqual(
    resolveSingleValueIconBox({ rowWidth: 0, fontSize, textWidth, size: 'medium' }).visible,
    true,
  );
  const wide = resolveSingleValueIconBox({
    rowWidth: 400,
    fontSize,
    textWidth,
    size: 'medium',
  });
  assert.equal(wide.visible, true);
  assert.equal(wide.size, Math.round(medium * 10) / 10);

  const large = resolveSingleValueIconBox({
    rowWidth: 400,
    fontSize: 80,
    textWidth,
    size: 'large',
  });
  assert.ok(large.size > medium);

  const tight = resolveSingleValueIconBox({
    rowWidth: textWidth + 25 + fontSize * SINGLE_VALUE_ICON_GAP_RATIO,
    fontSize,
    textWidth,
    size: 'medium',
  });
  assert.equal(tight.visible, true);
  assert.ok(tight.size < medium);
  assert.equal(tight.gap, fontSize * SINGLE_VALUE_ICON_GAP_RATIO);

  const landscape = resolveSingleValueIconBox({
    // 宽高比 2 时所需宽度更大；留给 minScale 之上、desired 之下的一段，验证先缩再隐
    rowWidth: textWidth + 50 + fontSize * SINGLE_VALUE_ICON_GAP_RATIO,
    fontSize,
    textWidth,
    size: 'medium',
    aspect: 2,
  });
  assert.equal(landscape.visible, true);
  assert.ok(landscape.size < medium);
  assert.ok(landscape.width < medium * 2);

  const hidden = resolveSingleValueIconBox({
    rowWidth: textWidth + 4,
    fontSize,
    textWidth,
    size: 'small',
  });
  assert.equal(hidden.visible, false);
  assert.equal(hidden.size, 0);
});
