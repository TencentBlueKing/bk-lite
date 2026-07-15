'use client';

import { useEffect, useRef, useState } from 'react';
import { CaretDownFilled, GlobalOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useLocale } from '@/context/locale';

export type SigninLocaleKey = 'zh-Hans' | 'en';

interface LanguageOption {
  key: SigninLocaleKey;
  nativeLabel: string;
}

const SUPPORTED_LANGUAGES: ReadonlyArray<LanguageOption> = [
  { key: 'zh-Hans', nativeLabel: '简体中文' },
  { key: 'en', nativeLabel: 'English' },
];

/**
 * 登录页双语切换控件。
 *
 * 设计迭代记录(同一组件,视觉契约演进):
 *   v1:antd <Dropdown>(portal 浮层)—— trigger 与 dropdown 视觉断开,失败。
 *   v2:inline popover —— 撑高容器挤下方,失败。
 *   v3(早期):trigger 与 dropdown 两个独立圆角胶囊 absolute 浮出——
 *      不挤,但中间有 4px 间距"奇怪不连"。
 *   v3.x(当前):trigger 与 dropdown 共边对接——
 *      关闭时 trigger 是独立圆角胶囊(低调);
 *      打开时 trigger 用 `rounded-t-xl + border-b-0`,
 *      dropdown 用 `rounded-b-xl + border-t-0`,
 *      二者背景都是 `bg-white/95`,trigger 顶部圆角 + dropdown 底部圆角,
 *      视觉上是一张完整"卡",共享的中间边双向 border 去掉 0 间距衔接。
 *      dropdown 仍 absolute(不参与文档流、不挤下方)。
 *
 * 行为契约:
 *   - 不引入 fetch / useSession / try-catch / async 副作用。
 *   - 仅作为 useLocale().setLocale 的触发器;副作用收敛到
 *     LocaleProvider.changeLocale。
 *   - Dropdown 项过滤当前 locale,只展示另一语言。
 *   - aria-label 走 signin.languageToggle.label(i18n 键)。
 *   - 后端 User.locale 持久化由个人设置 console_mgmt/update_user_base_info,
 *     登录页 toggle 只改前端 localStorage,登录后由后端按 user.locale 渲染。
 *     (曾尝试 syncBackendLocale→editUser/update_user,但该接口受
 *     user_group-Edit User 限制,会越权 / 清空 profile,故撤销。)
 */
export default function SigninLanguageToggle() {
  const { t } = useTranslation();
  const { locale, setLocale } = useLocale();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const handler = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => {
      document.removeEventListener('mousedown', handler);
    };
  }, [open]);

  const current: LanguageOption =
    SUPPORTED_LANGUAGES.find((lang) => lang.key === locale) ??
    SUPPORTED_LANGUAGES[0];

  // 关闭:独立圆角胶囊,色调低调。
  // 打开:与下方 dropdown 接合成"完整一张卡"。
  const triggerClassName = [
    'flex w-full items-center gap-2 px-3 py-2 text-sm',
    'text-(--color-text-1) backdrop-blur-[16px] transition-colors',
    open
      ? 'rounded-t-lg border-[1.5px] border-b-0 border-white/90 bg-[linear-gradient(180deg,rgba(255,255,255,0.16)_0%,rgba(255,255,255,0.07)_100%)] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.32)]'
      : 'rounded-lg border-[1.5px] border-white/90 bg-[linear-gradient(180deg,rgba(255,255,255,0.16)_0%,rgba(255,255,255,0.07)_100%)] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.32)] hover:bg-[linear-gradient(180deg,rgba(255,255,255,0.24)_0%,rgba(82,139,255,0.12)_100%)]',
  ].join(' ');

  return (
    <div ref={containerRef} className="relative inline-block text-left">
      <button
        type="button"
        aria-label={t('signin.languageToggle.label')}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={triggerClassName}
      >
        <GlobalOutlined aria-hidden />
        <span>{current.nativeLabel}</span>
        <CaretDownFilled
          aria-hidden
          className={`text-[10px] text-(--color-text-2) transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <ul
          role="menu"
          className="absolute right-0 top-full z-10 min-w-full overflow-hidden rounded-b-lg border-[1.5px] border-t-0 border-white/90 bg-[linear-gradient(180deg,rgba(255,255,255,0.16)_0%,rgba(255,255,255,0.07)_100%)] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.32)] backdrop-blur-[16px]"
        >
          {SUPPORTED_LANGUAGES.filter((lang) => lang.key !== locale).map(
            (lang) => (
              <li key={lang.key}>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setLocale(lang.key);
                    setOpen(false);
                  }}
                  className="flex w-full items-center px-3 py-2 text-left text-sm text-(--color-text-1) hover:bg-white/10"
                >
                  {lang.nativeLabel}
                </button>
              </li>
            ),
          )}
        </ul>
      )}
    </div>
  );
}
