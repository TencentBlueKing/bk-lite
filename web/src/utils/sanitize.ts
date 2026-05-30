import DOMPurify from 'dompurify';

/**
 * 公共 HTML 净化工具，统一防御存储型 / 反射型 XSS。
 *
 * 用于所有需要把字符串当 HTML 注入 DOM 的场景（dangerouslySetInnerHTML、
 * element.innerHTML 等），尤其是 Markdown 渲染、知识库预览、聊天消息等
 * 包含用户可控内容的位置。
 *
 * 统一禁用：
 *  - 事件处理属性（onerror / onload / onclick ... 任意 on* 属性）
 *  - javascript: / data: 等危险 URL 协议（DOMPurify 默认拦截，额外显式收紧）
 *  - <script> / <iframe> / <object> / <embed> 等可执行/可加载外部资源标签
 *  - 危险的 SVG / MathML 内联向量（通过 USE_PROFILES.html 仅允许 HTML 档案）
 */

// 统一禁止的事件属性（覆盖常见 on* 事件），作为 DOMPurify 默认行为之上的显式兜底。
const FORBID_EVENT_ATTR: string[] = [
  'onerror',
  'onload',
  'onclick',
  'ondblclick',
  'onmouseover',
  'onmouseout',
  'onmousemove',
  'onmousedown',
  'onmouseup',
  'onfocus',
  'onblur',
  'onchange',
  'oninput',
  'onsubmit',
  'onreset',
  'onkeydown',
  'onkeyup',
  'onkeypress',
  'onwheel',
  'onscroll',
  'oncontextmenu',
  'onanimationstart',
  'onanimationend',
  'ontransitionend',
  'onpointerdown',
  'onpointerup',
  'onpointermove',
  'ontouchstart',
  'ontouchend',
  'ontouchmove',
];

// 危险标签：可执行脚本或加载外部资源 / 危险向量图与表单交互。
const FORBID_DANGEROUS_TAGS: string[] = [
  'script',
  'style',
  'iframe',
  'object',
  'embed',
  'base',
  'form',
  'meta',
  'link',
  'svg',
  'math',
];

export interface SanitizeOptions {
  /**
   * 额外允许的标签（在默认 html 档案基础上追加）。
   */
  allowTags?: string[];
  /**
   * 额外允许的属性。
   */
  allowAttrs?: string[];
  /**
   * 是否允许 data-* 属性。默认 false。
   */
  allowDataAttr?: boolean;
}

/**
 * 默认净化：基于 DOMPurify 的 html 档案，禁用所有 on* 事件属性、
 * javascript:/data: 协议、script/iframe/svg/math 等危险标签。
 *
 * 适用于绝大多数 Markdown / 富文本渲染场景，正常的标题、列表、代码块、
 * 链接、图片、表格等都会被保留。
 */
export const sanitizeHtml = (
  dirty: string | null | undefined,
  options: SanitizeOptions = {}
): string => {
  if (!dirty) return '';

  return DOMPurify.sanitize(dirty, {
    USE_PROFILES: { html: true },
    ADD_TAGS: options.allowTags,
    ADD_ATTR: options.allowAttrs,
    FORBID_ATTR: FORBID_EVENT_ATTR,
    FORBID_TAGS: FORBID_DANGEROUS_TAGS,
    ALLOW_DATA_ATTR: options.allowDataAttr ?? false,
    // 仅允许安全的链接/资源协议，杜绝 javascript:、vbscript:、data: 脚本注入。
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel|ftp):|[^a-z]|[a-z+.-]+(?:[^a-z+.\-:]|$))/i,
  });
};

/**
 * 转义字符串中的 HTML 特殊字符，使其作为纯文本安全展示。
 *
 * 用于需要在已净化的 HTML 模板里插值用户输入（如搜索高亮、代码片段高亮）
 * 的场景：先转义用户内容，再拼接受信任的标记标签（<mark>/<span>）。
 */
export const escapeHtml = (value: string | null | undefined): string => {
  if (!value) return '';
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};

export default sanitizeHtml;
