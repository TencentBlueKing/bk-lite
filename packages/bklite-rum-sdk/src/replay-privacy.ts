type JsonObject = Record<string, unknown>;

const REDACTED_TEXT = '[redacted]';
const MAX_REPLAY_TEXT_BYTES = 1024 * 1024;
const MAX_SAFE_INTEGER = Number.MAX_SAFE_INTEGER;
const SAFE_REPLAY_ATTRIBUTES = new Set(
  `autofocus checked colspan controls dir disabled height hidden lang loop max maxlength min
   minlength multiple open readonly required reversed role rowspan selected size step type width`.split(
    /\s+/,
  ),
);
const SAFE_REPLAY_CSS_PROPERTIES = new Set(
  `align-content align-items align-self alignment-baseline appearance aspect-ratio
   backface-visibility background-color border border-block border-block-color border-block-end
   border-block-end-color border-block-end-style border-block-end-width border-block-start
   border-block-start-color border-block-start-style border-block-start-width border-block-style
   border-block-width border-bottom border-bottom-color border-bottom-left-radius
   border-bottom-right-radius border-bottom-style border-bottom-width border-collapse border-color
   border-end-end-radius border-end-start-radius border-inline border-inline-color border-inline-end
   border-inline-end-color border-inline-end-style border-inline-end-width border-inline-start
   border-inline-start-color border-inline-start-style border-inline-start-width border-inline-style
   border-inline-width border-left border-left-color border-left-style border-left-width border-radius
   border-right border-right-color border-right-style border-right-width border-spacing
   border-start-end-radius border-start-start-radius border-style border-top border-top-color
   border-top-left-radius border-top-right-radius border-top-style border-top-width border-width bottom
   box-shadow box-sizing caption-side clear color color-scheme column-count column-fill column-gap
   column-rule column-rule-color column-rule-style column-rule-width column-span column-width columns
   direction display dominant-baseline empty-cells fill fill-opacity fill-rule flex flex-basis
   flex-direction flex-flow flex-grow flex-shrink flex-wrap float flood-color flood-opacity font
   font-family font-feature-settings font-kerning font-optical-sizing font-size font-size-adjust
   font-stretch font-style font-variant font-variant-caps font-weight gap grid grid-area
   grid-auto-columns grid-auto-flow grid-auto-rows grid-column grid-column-end grid-column-start grid-row
   grid-row-end grid-row-start grid-template grid-template-areas grid-template-columns
   grid-template-rows height hyphens inset inset-block inset-block-end inset-block-start inset-inline
   inset-inline-end inset-inline-start isolation justify-content justify-items justify-self left
   letter-spacing lighting-color line-height list-style-position list-style-type margin margin-block
   margin-block-end margin-block-start margin-bottom margin-inline margin-inline-end margin-inline-start
   margin-left margin-right margin-top max-block-size max-height max-inline-size max-width min-block-size
   min-height min-inline-size min-width object-fit object-position opacity order outline outline-color
   outline-offset outline-style outline-width overflow overflow-anchor overflow-block overflow-inline
   overflow-wrap overflow-x overflow-y padding padding-block padding-block-end padding-block-start
   padding-bottom padding-inline padding-inline-end padding-inline-start padding-left padding-right
   padding-top paint-order perspective perspective-origin place-content place-items place-self position
   right row-gap shape-rendering stop-color stop-opacity stroke stroke-dasharray stroke-dashoffset
   stroke-linecap stroke-linejoin stroke-miterlimit stroke-opacity stroke-width tab-size table-layout
   text-align text-align-last text-anchor text-decoration text-decoration-color text-decoration-line
   text-decoration-style text-decoration-thickness text-indent text-overflow text-shadow
   text-size-adjust text-transform text-underline-offset top transform transform-box transform-origin
   transform-style unicode-bidi vector-effect vertical-align visibility white-space width word-break
   word-spacing word-wrap writing-mode z-index -moz-osx-font-smoothing -webkit-appearance
   -webkit-font-smoothing -webkit-text-size-adjust -webkit-transform -webkit-transform-origin`.split(
    /\s+/,
  ),
);
const SAFE_REPLAY_CSS_FUNCTIONS = new Set(
  `calc clamp color color-mix env fit-content hsl hsla hwb lab lch matrix matrix3d max min minmax
   oklab oklch perspective repeat rgb rgba rotate rotate3d rotatex rotatey rotatez scale scale3d
   scalex scaley scalez skew skewx skewy translate translate3d translatex translatey translatez var`.split(
    /\s+/,
  ),
);
const SAFE_SVG_ATTRIBUTES = new Set(
  `alignment-baseline cx cy d dominant-baseline dx dy fill fill-opacity fill-rule font-family
   font-size font-style font-weight gradienttransform gradientunits height lengthadjust offset opacity
   paint-order pathlength points preserveaspectratio r rx ry shape-rendering spreadmethod stop-color
   stop-opacity stroke stroke-dasharray stroke-dashoffset stroke-linecap stroke-linejoin
   stroke-miterlimit stroke-opacity stroke-width text-anchor textlength transform transform-origin
   vector-effect viewbox visibility width x x1 x2 y y1 y2`.split(/\s+/),
);
const FORBIDDEN_CSS =
  /(?:url\s*\(|@import\b|@font-face\b|expression\s*\(|image(?:-set)?\s*\(|cross-fade\s*\(|element\s*\(|paint\s*\(|-moz-binding\b|behavior\s*:|javascript\s*:|data\s*:|blob\s*:|https?\s*:|\/\*)/i;
const SAFE_SELECTOR = /^[-A-Za-z0-9\s._:(),>+~*]+$/;
const SAFE_AT_RULE_CONDITION = /^[-A-Za-z0-9\s._:(),/%+~*]+$/;

function asObject(value: unknown): JsonObject | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as JsonObject)
    : undefined;
}

function finiteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value)
    ? value
    : undefined;
}

function integer(value: unknown, minimum = 0): number | undefined {
  return typeof value === 'number' &&
    Number.isSafeInteger(value) &&
    value >= minimum &&
    value <= MAX_SAFE_INTEGER
    ? value
    : undefined;
}

function finiteFields(
  source: JsonObject,
  names: string[],
): JsonObject | undefined {
  const output: JsonObject = {};
  for (const name of names) {
    const value = finiteNumber(source[name]);
    if (value === undefined) return undefined;
    output[name] = value;
  }
  return output;
}

function integerFields(
  source: JsonObject,
  names: string[],
  minimum = 0,
): JsonObject | undefined {
  const output: JsonObject = {};
  for (const name of names) {
    const value = integer(source[name], minimum);
    if (value === undefined) return undefined;
    output[name] = value;
  }
  return output;
}

function redactText(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  return value.length === 0 ? '' : REDACTED_TEXT;
}

function readableText(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  return new TextEncoder().encode(value).byteLength <= MAX_REPLAY_TEXT_BYTES
    ? value
    : undefined;
}

function decodeCssEscapes(input: string): string | undefined {
  let output = '';
  for (let index = 0; index < input.length; index += 1) {
    const character = input[index] as string;
    if (character !== '\\') {
      output += character;
      continue;
    }
    index += 1;
    if (index >= input.length) return undefined;
    const escaped = input[index] as string;
    if (escaped === '\n' || escaped === '\r' || escaped === '\f')
      return undefined;
    if (!/[0-9a-f]/i.test(escaped)) {
      output += escaped;
      continue;
    }
    let hex = escaped;
    while (
      hex.length < 6 &&
      index + 1 < input.length &&
      /[0-9a-f]/i.test(input[index + 1] as string)
    ) {
      index += 1;
      hex += input[index];
    }
    const codePoint = Number.parseInt(hex, 16);
    if (codePoint === 0 || codePoint > 0x10ffff) return undefined;
    output += String.fromCodePoint(codePoint);
    if (
      index + 1 < input.length &&
      /[\t\n\f\r ]/.test(input[index + 1] as string)
    )
      index += 1;
  }
  return output;
}

function containsCssRequestSyntax(value: string): boolean {
  const decoded = decodeCssEscapes(value);
  if (decoded === undefined) return true;
  return /(?:^|[;{])\s*@(import|font-face)\b|(?:url|image-set|cross-fade|element|paint)\s*\(/i.test(
    decoded,
  );
}

function hasControlCharacter(
  value: string,
  allowCssWhitespace: boolean,
): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code === 0x7f) return true;
    if (code >= 0x20) continue;
    if (allowCssWhitespace && (code === 0x09 || code === 0x0a || code === 0x0d))
      continue;
    return true;
  }
  return false;
}

function safePrintableString(
  value: unknown,
  maximumBytes = 4096,
): string | undefined {
  if (
    typeof value !== 'string' ||
    new TextEncoder().encode(value).byteLength > maximumBytes ||
    hasControlCharacter(value, false)
  ) {
    return undefined;
  }
  return value;
}

function safeCssValue(value: string): boolean {
  if (
    value.length > 16 * 1024 ||
    hasControlCharacter(value, true) ||
    FORBIDDEN_CSS.test(value)
  ) {
    return false;
  }
  for (const match of value.matchAll(/(-?[A-Za-z][A-Za-z0-9-]*)\s*\(/g)) {
    if (!SAFE_REPLAY_CSS_FUNCTIONS.has(match[1]!.toLowerCase())) return false;
  }
  return true;
}

function sanitizeCssDeclaration(
  rawProperty: unknown,
  rawValue: unknown,
  rawPriority: unknown = '',
): { priority: string; property: string; value: string } | undefined {
  if (typeof rawProperty !== 'string' || typeof rawValue !== 'string')
    return undefined;
  const property = rawProperty.trim().toLowerCase();
  const priority =
    rawPriority === 'important'
      ? 'important'
      : rawPriority === ''
        ? ''
        : undefined;
  if (
    !SAFE_REPLAY_CSS_PROPERTIES.has(property) ||
    priority === undefined ||
    !safeCssValue(rawValue)
  ) {
    return undefined;
  }
  if (typeof document === 'undefined') return undefined;

  const probe = document.createElement('span').style;
  probe.setProperty(property, rawValue, priority);
  const value = probe.getPropertyValue(property);
  if (!value || !safeCssValue(value)) return undefined;
  return { priority: probe.getPropertyPriority(property), property, value };
}

function sanitizeStyleDeclaration(style: CSSStyleDeclaration): string {
  if (typeof document === 'undefined') return '';
  const output = document.createElement('span').style;
  for (const property of Array.from(style)) {
    const sanitized = sanitizeCssDeclaration(
      property,
      style.getPropertyValue(property),
      style.getPropertyPriority(property),
    );
    if (sanitized) {
      output.setProperty(
        sanitized.property,
        sanitized.value,
        sanitized.priority,
      );
    }
  }
  return output.cssText;
}

function sanitizeInlineCss(value: unknown): string | undefined {
  if (
    typeof value !== 'string' ||
    value.length > 64 * 1024 ||
    typeof document === 'undefined'
  ) {
    return undefined;
  }
  const source = document.createElement('span').style;
  source.cssText = value;
  return sanitizeStyleDeclaration(source);
}

function sanitizeSelector(value: string): string | undefined {
  const selector = value.trim();
  return selector.length > 0 &&
    selector.length <= 4096 &&
    SAFE_SELECTOR.test(selector)
    ? selector
    : undefined;
}

function sanitizeCssRuleList(rules: CSSRuleList): string {
  const output: string[] = [];
  for (const rule of Array.from(rules)) {
    if (rule.type === 1) {
      const styleRule = rule as CSSStyleRule;
      const selector = sanitizeSelector(styleRule.selectorText);
      const declarations = sanitizeStyleDeclaration(styleRule.style);
      if (selector && declarations) output.push(`${selector}{${declarations}}`);
      continue;
    }
    if (rule.type === 4 || rule.type === 12) {
      const group = rule as CSSMediaRule | CSSSupportsRule;
      const condition = group.conditionText.trim();
      if (
        condition.length > 0 &&
        condition.length <= 4096 &&
        SAFE_AT_RULE_CONDITION.test(condition) &&
        !FORBIDDEN_CSS.test(condition)
      ) {
        const nested = sanitizeCssRuleList(group.cssRules);
        if (nested)
          output.push(
            `@${rule.type === 4 ? 'media' : 'supports'} ${condition}{${nested}}`,
          );
      }
    }
  }
  return output.join('');
}

function sanitizeStylesheetCss(value: unknown): string | undefined {
  if (
    typeof value !== 'string' ||
    value.length > 1024 * 1024 ||
    typeof CSSStyleSheet === 'undefined'
  ) {
    return undefined;
  }
  try {
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(value);
    return sanitizeCssRuleList(sheet.cssRules);
  } catch {
    return '';
  }
}

function sanitizeStyleAttribute(value: unknown): unknown {
  if (typeof value === 'string') return sanitizeInlineCss(value);
  const source = asObject(value);
  if (!source) return undefined;
  const output: JsonObject = {};
  for (const [rawProperty, rawValue] of Object.entries(source)) {
    if (rawValue === false) {
      if (SAFE_REPLAY_CSS_PROPERTIES.has(rawProperty.toLowerCase()))
        output[rawProperty] = false;
      continue;
    }
    const tuple = Array.isArray(rawValue) ? rawValue : [rawValue, ''];
    if (tuple.length !== 2) continue;
    const sanitized = sanitizeCssDeclaration(rawProperty, tuple[0], tuple[1]);
    if (!sanitized) continue;
    output[sanitized.property] = Array.isArray(rawValue)
      ? [sanitized.value, sanitized.priority]
      : sanitized.value;
  }
  return output;
}

function sanitizeRrAttribute(name: string, value: unknown): unknown {
  if (name === 'rr_mediastate')
    return value === 'played' || value === 'paused' ? value : undefined;
  if (name === 'rr_open_mode')
    return value === 'modal' || value === 'non-modal' ? value : undefined;
  if (name === 'rr_mediamuted' || name === 'rr_medialoop') {
    return typeof value === 'boolean' ? value : undefined;
  }
  if (
    name === 'rr_mediacurrenttime' ||
    name === 'rr_mediaplaybackrate' ||
    name === 'rr_mediavolume' ||
    name === 'rr_scrollleft' ||
    name === 'rr_scrolltop'
  ) {
    return finiteNumber(value);
  }
  if (name === 'rr_width' || name === 'rr_height') {
    return typeof value === 'string' && /^[0-9]+(?:\.[0-9]+)?px$/.test(value)
      ? value
      : undefined;
  }
  return undefined;
}

function sanitizeAttributes(value: unknown): JsonObject | undefined {
  const source = asObject(value);
  if (!source) return undefined;
  const output: JsonObject = {};
  for (const [rawName, rawValue] of Object.entries(source)) {
    const name = rawName.toLowerCase();
    if (name === 'class') {
      const value = safePrintableString(rawValue, 2048)
        ?.trim()
        .split(/\s+/)
        .slice(0, 64)
        .join(' ');
      if (value) output.class = value;
      continue;
    }
    if (name === 'style') {
      const value = sanitizeStyleAttribute(rawValue);
      if (value !== undefined) output.style = value;
      continue;
    }
    if (name === '_csstext') {
      const value = sanitizeStylesheetCss(rawValue);
      if (value !== undefined) output._cssText = value;
      continue;
    }
    if (name.startsWith('rr_')) {
      const value = sanitizeRrAttribute(name, rawValue);
      if (value !== undefined) output[rawName] = value;
      continue;
    }
    if (SAFE_SVG_ATTRIBUTES.has(name)) {
      const value = safePrintableString(rawValue, 16 * 1024);
      if (value !== undefined && !FORBIDDEN_CSS.test(value))
        output[rawName] = value;
      continue;
    }
    if (!SAFE_REPLAY_ATTRIBUTES.has(name)) continue;
    if (
      rawValue === null ||
      typeof rawValue === 'boolean' ||
      typeof rawValue === 'number'
    ) {
      output[rawName] = rawValue;
      continue;
    }
    const value = safePrintableString(rawValue);
    if (value !== undefined) output[rawName] = value;
  }
  return output;
}

function sanitizeNode(value: unknown, depth = 0): JsonObject | undefined {
  if (depth > 64) return undefined;
  const source = asObject(value);
  const type = integer(source?.type);
  const id = integer(source?.id, 1);
  if (!source || type === undefined || id === undefined || type > 5)
    return undefined;

  const output: JsonObject = { id, type };
  const rootId = integer(source.rootId, 1);
  if (rootId !== undefined) output.rootId = rootId;
  for (const name of ['isShadowHost', 'isShadow'] as const) {
    if (typeof source[name] === 'boolean') output[name] = source[name];
  }

  if (type === 0 || type === 2) {
    if (!Array.isArray(source.childNodes)) return undefined;
    const childNodes: JsonObject[] = [];
    for (const child of source.childNodes) {
      const sanitized = sanitizeNode(child, depth + 1);
      if (!sanitized) return undefined;
      childNodes.push(sanitized);
    }
    output.childNodes = childNodes;
  }

  if (type === 0) {
    if (
      source.compatMode === 'CSS1Compat' ||
      source.compatMode === 'BackCompat'
    ) {
      output.compatMode = source.compatMode;
    }
    return output;
  }
  if (type === 1) {
    const name = safePrintableString(source.name, 64);
    if (!name) return undefined;
    output.name = name;
    output.publicId = '';
    output.systemId = '';
    return output;
  }
  if (type === 2) {
    const tagName = safePrintableString(source.tagName, 64);
    const attributes = sanitizeAttributes(source.attributes);
    if (!tagName || !attributes) return undefined;
    output.tagName = tagName;
    output.attributes = attributes;
    for (const name of ['isSVG', 'needBlock', 'isCustom'] as const) {
      if (typeof source[name] === 'boolean') output[name] = source[name];
    }
    return output;
  }

  const textContent =
    source.isStyle === true
      ? sanitizeStylesheetCss(source.textContent)
      : type === 3
        ? readableText(source.textContent)
        : redactText(source.textContent);
  if (textContent === undefined) return undefined;
  output.textContent = textContent;
  if (source.isStyle === true) output.isStyle = true;
  return output;
}

function sanitizeIndex(value: unknown): number | number[] | undefined {
  const scalar = integer(value);
  if (scalar !== undefined) return scalar;
  if (!Array.isArray(value)) return undefined;
  const output: number[] = [];
  for (const item of value) {
    const parsed = integer(item);
    if (parsed === undefined) return undefined;
    output.push(parsed);
  }
  return output;
}

function sanitizeMutationData(source: JsonObject): JsonObject | undefined {
  if (
    !Array.isArray(source.texts) ||
    !Array.isArray(source.attributes) ||
    !Array.isArray(source.removes) ||
    !Array.isArray(source.adds)
  ) {
    return undefined;
  }
  const texts: JsonObject[] = [];
  for (const entry of source.texts) {
    const item = asObject(entry);
    const id = integer(item?.id, 1);
    const readable = item?.value === null ? null : readableText(item?.value);
    const value =
      readable === null
        ? null
        : readable === undefined
          ? undefined
          : containsCssRequestSyntax(readable)
            ? REDACTED_TEXT
            : readable;
    if (!item || id === undefined || value === undefined) return undefined;
    texts.push({ id, value });
  }
  const attributes: JsonObject[] = [];
  for (const entry of source.attributes) {
    const item = asObject(entry);
    const id = integer(item?.id, 1);
    const values = sanitizeAttributes(item?.attributes);
    if (!item || id === undefined || !values) return undefined;
    attributes.push({ attributes: values, id });
  }
  const removes: JsonObject[] = [];
  for (const entry of source.removes) {
    const item = asObject(entry);
    const ids = item ? integerFields(item, ['parentId', 'id'], 1) : undefined;
    if (!item || !ids) return undefined;
    if (typeof item.isShadow === 'boolean') ids.isShadow = item.isShadow;
    removes.push(ids);
  }
  const adds: JsonObject[] = [];
  for (const entry of source.adds) {
    const item = asObject(entry);
    const parentId = integer(item?.parentId, 1);
    const nextId = item?.nextId === null ? null : integer(item?.nextId, -1);
    const node = sanitizeNode(item?.node);
    if (!item || parentId === undefined || nextId === undefined || !node)
      return undefined;
    const output: JsonObject = { nextId, node, parentId };
    if (item.previousId === null) output.previousId = null;
    else {
      const previousId = integer(item.previousId, -1);
      if (previousId !== undefined) output.previousId = previousId;
    }
    adds.push(output);
  }
  const output: JsonObject = { adds, attributes, removes, source: 0, texts };
  if (typeof source.isAttachIframe === 'boolean')
    output.isAttachIframe = source.isAttachIframe;
  return output;
}

function sanitizePositionData(
  source: JsonObject,
  incrementalSource: number,
): JsonObject | undefined {
  if (!Array.isArray(source.positions)) return undefined;
  const positions: JsonObject[] = [];
  for (const entry of source.positions) {
    const item = asObject(entry);
    const values = item
      ? finiteFields(item, ['x', 'y', 'timeOffset'])
      : undefined;
    const id = integer(item?.id, 1);
    if (!item || !values || id === undefined) return undefined;
    positions.push({ ...values, id });
  }
  return { positions, source: incrementalSource };
}

function sanitizeStyleRuleData(source: JsonObject): JsonObject | undefined {
  const output: JsonObject = { source: 8 };
  for (const name of ['id', 'styleId'] as const) {
    const value = integer(source[name], 1);
    if (value !== undefined) output[name] = value;
  }
  if (source.removes !== undefined) {
    if (!Array.isArray(source.removes)) return undefined;
    const removes: JsonObject[] = [];
    for (const entry of source.removes) {
      const item = asObject(entry);
      const index = sanitizeIndex(item?.index);
      if (!item || index === undefined) return undefined;
      removes.push({ index });
    }
    output.removes = removes;
  }
  if (source.adds !== undefined) {
    if (!Array.isArray(source.adds)) return undefined;
    const adds: JsonObject[] = [];
    for (const entry of source.adds) {
      const item = asObject(entry);
      const rule = sanitizeStylesheetCss(item?.rule);
      if (!item || rule === undefined) return undefined;
      if (!rule) continue;
      const sanitized: JsonObject = { rule };
      const index = sanitizeIndex(item.index);
      if (index !== undefined) sanitized.index = index;
      adds.push(sanitized);
    }
    output.adds = adds;
  }
  for (const name of ['replace', 'replaceSync'] as const) {
    if (source[name] === undefined) continue;
    const value = sanitizeStylesheetCss(source[name]);
    if (value === undefined) return undefined;
    output[name] = value;
  }
  return output;
}

function sanitizeStyleDeclarationData(
  source: JsonObject,
): JsonObject | undefined {
  const index = sanitizeIndex(source.index);
  if (index === undefined) return undefined;
  const output: JsonObject = { index, source: 13 };
  for (const name of ['id', 'styleId'] as const) {
    const value = integer(source[name], 1);
    if (value !== undefined) output[name] = value;
  }
  if (source.set !== undefined) {
    const set = asObject(source.set);
    if (!set) return undefined;
    const value = set.value === null ? undefined : set.value;
    const sanitized = sanitizeCssDeclaration(
      set.property,
      value,
      set.priority ?? '',
    );
    if (sanitized) output.set = sanitized;
  }
  if (source.remove !== undefined) {
    const remove = asObject(source.remove);
    const property =
      typeof remove?.property === 'string' ? remove.property.toLowerCase() : '';
    if (SAFE_REPLAY_CSS_PROPERTIES.has(property)) output.remove = { property };
  }
  return output;
}

function sanitizeAdoptedStyleData(source: JsonObject): JsonObject | undefined {
  const id = integer(source.id, 1);
  if (id === undefined || !Array.isArray(source.styleIds)) return undefined;
  const styleIds: number[] = [];
  for (const value of source.styleIds) {
    const styleId = integer(value, 1);
    if (styleId === undefined) return undefined;
    styleIds.push(styleId);
  }
  const output: JsonObject = { id, source: 15, styleIds };
  if (source.styles === undefined) return output;
  if (!Array.isArray(source.styles)) return undefined;
  const styles: JsonObject[] = [];
  for (const entry of source.styles) {
    const style = asObject(entry);
    const styleId = integer(style?.styleId, 1);
    if (!style || styleId === undefined || !Array.isArray(style.rules))
      return undefined;
    const rules: JsonObject[] = [];
    for (const entry of style.rules) {
      const item = asObject(entry);
      const rule = sanitizeStylesheetCss(item?.rule);
      if (!item || rule === undefined) return undefined;
      if (!rule) continue;
      const sanitized: JsonObject = { rule };
      const index = sanitizeIndex(item.index);
      if (index !== undefined) sanitized.index = index;
      rules.push(sanitized);
    }
    styles.push({ rules, styleId });
  }
  output.styles = styles;
  return output;
}

function sanitizeIncrementalData(value: unknown): JsonObject | undefined {
  const source = asObject(value);
  const incrementalSource = integer(source?.source);
  if (!source || incrementalSource === undefined || incrementalSource > 16)
    return undefined;
  if (incrementalSource === 0) return sanitizeMutationData(source);
  if (
    incrementalSource === 1 ||
    incrementalSource === 6 ||
    incrementalSource === 12
  ) {
    return sanitizePositionData(source, incrementalSource);
  }
  if (incrementalSource === 2) {
    const values = finiteFields(source, ['x', 'y']) ?? {};
    const identity = integerFields(source, ['type', 'id']);
    if (!identity) return undefined;
    const output: JsonObject = { ...identity, ...values, source: 2 };
    const pointerType = integer(source.pointerType);
    if (pointerType !== undefined && pointerType <= 2)
      output.pointerType = pointerType;
    return output;
  }
  if (incrementalSource === 3) {
    const values = finiteFields(source, ['x', 'y']);
    const id = integer(source.id, 1);
    return values && id !== undefined
      ? { ...values, id, source: 3 }
      : undefined;
  }
  if (incrementalSource === 4) {
    const values = finiteFields(source, ['width', 'height']);
    return values ? { ...values, source: 4 } : undefined;
  }
  if (incrementalSource === 5) {
    const id = integer(source.id, 1);
    const text = redactText(source.text);
    if (
      id === undefined ||
      text === undefined ||
      typeof source.isChecked !== 'boolean'
    ) {
      return undefined;
    }
    const output: JsonObject = {
      id,
      isChecked: source.isChecked,
      source: 5,
      text,
    };
    if (typeof source.userTriggered === 'boolean')
      output.userTriggered = source.userTriggered;
    return output;
  }
  if (incrementalSource === 7) {
    const identity = integerFields(source, ['type', 'id']);
    if (!identity) return undefined;
    const output: JsonObject = { ...identity, source: 7 };
    for (const name of ['currentTime', 'volume', 'playbackRate'] as const) {
      const value = finiteNumber(source[name]);
      if (value !== undefined) output[name] = value;
    }
    for (const name of ['muted', 'loop'] as const) {
      if (typeof source[name] === 'boolean') output[name] = source[name];
    }
    return output;
  }
  if (incrementalSource === 8) return sanitizeStyleRuleData(source);
  if (
    incrementalSource === 9 ||
    incrementalSource === 10 ||
    incrementalSource === 11
  ) {
    return undefined;
  }
  if (incrementalSource === 13) return sanitizeStyleDeclarationData(source);
  if (incrementalSource === 14) {
    if (!Array.isArray(source.ranges)) return undefined;
    const ranges: JsonObject[] = [];
    for (const entry of source.ranges) {
      const range = asObject(entry);
      const values = range
        ? integerFields(range, ['start', 'startOffset', 'end', 'endOffset'])
        : undefined;
      if (!values) return undefined;
      ranges.push(values);
    }
    return { ranges, source: 14 };
  }
  if (incrementalSource === 15) return sanitizeAdoptedStyleData(source);
  if (incrementalSource === 16) {
    const define = asObject(source.define);
    const name = safePrintableString(define?.name, 64);
    return name && /^[a-z][a-z0-9._-]*-[a-z0-9._-]*$/.test(name)
      ? { define: { name }, source: 16 }
      : undefined;
  }
  return undefined;
}

/**
 * Browser-side, fail-closed privacy boundary for Faro Replay `beforeSend`.
 *
 * The receiver repeats stricter validation and sanitization as defense in depth. This first pass
 * preserves inert interface text while preventing input values, arbitrary attributes,
 * request-capable URLs, and unsafe CSS from leaving the customer's browser.
 */
export function sanitizeReplayEvent<T extends object>(event: T): T | null {
  const source = asObject(event);
  const type = integer(source?.type);
  const timestamp = finiteNumber(source?.timestamp);
  if (!source || type === undefined || type > 7 || timestamp === undefined)
    return null;

  let data: JsonObject | undefined;
  if (type === 0 || type === 1) {
    data = {};
  } else if (type === 2) {
    const fullSnapshot = asObject(source.data);
    const initialOffset = asObject(fullSnapshot?.initialOffset);
    const offset = initialOffset
      ? finiteFields(initialOffset, ['top', 'left'])
      : undefined;
    const node = sanitizeNode(fullSnapshot?.node);
    if (offset && node) data = { initialOffset: offset, node };
  } else if (type === 3) {
    data = sanitizeIncrementalData(source.data);
  } else if (type === 4) {
    const meta = asObject(source.data);
    const dimensions = meta
      ? finiteFields(meta, ['width', 'height'])
      : undefined;
    if (dimensions) data = { ...dimensions, href: 'about:blank' };
  } else {
    // Custom, Plugin, and Asset events can carry opaque caller-controlled strings.
    return null;
  }
  if (!data) return null;

  const output: JsonObject = { data, timestamp, type };
  if (source.delay !== undefined) {
    const delay = finiteNumber(source.delay);
    if (delay === undefined) return null;
    output.delay = delay;
  }
  return output as T;
}
