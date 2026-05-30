import DOMPurify from 'isomorphic-dompurify';

/**
 * 公共 HTML 净化工具，统一防御存储型 / 反射型 XSS。
 *
 * 移动端使用 isomorphic-dompurify 以兼容 SSR（服务端无 window 时回退到 jsdom）。
 * 用于所有需要把字符串当 HTML 注入 DOM 的场景（dangerouslySetInnerHTML 等），
 * 尤其是 Markdown 渲染、会话消息、搜索高亮等包含用户可控内容的位置。
 *
 * 统一禁用：
 *  - 事件处理属性（onerror / onload / onclick ... 任意 on* 属性）
 *  - javascript: / data: 等危险 URL 协议
 *  - <script> / <iframe> / <object> / <embed> / <svg> / <math> 等危险标签
 */

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
  allowTags?: string[];
  allowAttrs?: string[];
  allowDataAttr?: boolean;
}

/**
 * 默认净化：基于 DOMPurify 的 html 档案，禁用所有 on* 事件属性、
 * javascript:/data: 协议、script/iframe/svg/math 等危险标签。
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
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel|ftp):|[^a-z]|[a-z+.-]+(?:[^a-z+.\-:]|$))/i,
  });
};

/**
 * 转义字符串中的 HTML 特殊字符，使其作为纯文本安全展示。
 * 用于在受信任的 HTML 模板里插值用户输入（如搜索高亮）。
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
