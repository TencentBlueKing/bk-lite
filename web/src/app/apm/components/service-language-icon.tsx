'use client';

import type { ReactNode } from 'react';

export const LANGUAGE_LABELS: Record<string, string> = {
  cpp: 'C++',
  csharp: '.NET',
  dotnet: '.NET',
  go: 'Go',
  golang: 'Go',
  java: 'Java',
  javascript: 'JavaScript',
  js: 'JavaScript',
  nodejs: 'Node.js',
  node: 'Node.js',
  php: 'PHP',
  python: 'Python',
  ruby: 'Ruby',
  rust: 'Rust',
};

export function normalizeServiceLanguage(language?: string) {
  return language?.trim().toLowerCase() ?? '';
}

export function serviceLanguageLabel(language?: string, fallback = '') {
  const normalized = normalizeServiceLanguage(language);
  if (!normalized) return fallback;
  return LANGUAGE_LABELS[normalized] ?? language?.trim() ?? fallback;
}

interface LanguageIconProps {
  size?: number;
  className?: string;
  x?: number;
  y?: number;
}

function iconSvg(
  size: number,
  className: string | undefined,
  x: number | undefined,
  y: number | undefined,
  children: ReactNode,
  kind?: string,
) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      data-service-icon={kind}
      fill="none"
      height={size}
      viewBox="0 0 16 16"
      width={size}
      x={x}
      y={y}
    >
      {children}
    </svg>
  );
}

function PythonIcon({ size = 16, className, x, y }: LanguageIconProps) {
  return iconSvg(size, className, x, y, (
    <>
      <path d="M8.2 1.4c-2.6 0-2.4 1.1-2.4 1.1v1.6h2.5v.3H4.3S1.6 4.2 1.6 8c0 3.7 2 3.5 2 3.5h1.2V9.6S4.7 7.8 6.8 7.8h2.6s2-.1 2-2.2V3.4S11.6 1.4 8.2 1.4Z" fill="#3776AB" />
      <path d="M7.8 14.6c2.6 0 2.4-1.1 2.4-1.1v-1.6H7.7v-.3h3.9s2.7.2 2.7-3.6c0-3.7-2-3.5-2-3.5h-1.2v1.9s.1 1.8-2 1.8H6.5s-2 .1-2 2.2v2.2s-.2 2 3.3 2Z" fill="#FFD43B" />
      <circle cx="6.6" cy="3.2" fill="#fff" r="0.7" />
      <circle cx="9.4" cy="12.8" fill="#fff" r="0.7" />
    </>
  ));
}

function JavaIcon({ size = 16, className, x, y }: LanguageIconProps) {
  return iconSvg(size, className, x, y, (
    <>
      <path d="M4.8 10.1c0 1.6 2.6 2.1 3.9 2.1 1.9 0 3.6-.6 3.6-1.7 0-.6-.6-1-1.6-1.2-2.3.6-4.6.3-5.9.8Z" fill="#EA2D2E" />
      <path d="M10.6 8.6c-.9.5-2.6.8-3.8.4 1.1-.8 2.6-1 3.8-.4Z" fill="#EA2D2E" />
      <path d="M6.4 7.4c.9.8 2.4.6 3.2.1-.7-.6-2.1-.8-3.2-.1Z" fill="#EA2D2E" />
      <path d="M8.7 1.8s-.4 2.1 1.2 3.5c1.3 1.2-.2 2.1-.2 2.1s2.1-1.1 1-3C9.6 2.9 8.7 1.8 8.7 1.8Z" fill="#5382A1" />
      <path d="M7.6 4.4S6 5.8 7.4 7.2c1.2 1.2 0 1.9 0 1.9S5.2 7.8 6.3 6.2c.8-1.2 1.3-1.8 1.3-1.8Z" fill="#5382A1" />
      <path d="M3.4 12.5c.4 1.4 3.2 1.8 5.4 1.8 3.3 0 5-.9 5-1.7 0 0-.6 1.8-5.2 1.8-3.6 0-5.2-1.2-5.2-1.9Z" fill="#EA2D2E" />
    </>
  ));
}

function GoIcon({ size = 16, className, x, y }: LanguageIconProps) {
  return iconSvg(size, className, x, y, (
    <>
      <ellipse cx="8" cy="8.2" fill="#00ADD8" rx="6.4" ry="3.6" />
      <circle cx="5.8" cy="7.6" fill="#fff" r="0.7" />
      <circle cx="8.6" cy="7.6" fill="#fff" r="0.7" />
      <path d="M11.6 8.8c.8 0 1.6-.3 1.6-.8h.8c0 1-1.1 1.6-2.4 1.6-1.2 0-2.2-.5-2.2-1.3h.8c0 .3.6.5 1.4.5Z" fill="#00ADD8" />
    </>
  ));
}

function JavaScriptIcon({ size = 16, className, x, y }: LanguageIconProps) {
  return iconSvg(size, className, x, y, (
    <>
      <rect fill="#F7DF1E" height="14" rx="2" width="14" x="1" y="1" />
      <path d="M7.2 12.1c0 1.2-.7 1.8-1.8 1.8-.9 0-1.5-.5-1.8-1.1l1-.6c.2.3.4.6.8.6.4 0 .6-.2.6-.7V7.6h1.2v4.5Zm2.4 1.8c-1.1 0-1.8-.5-2.2-1.2l1-.6c.3.5.6.8 1.2.8.5 0 .8-.2.8-.6 0-.4-.3-.6-1-.8l-.4-.2c-1-.4-1.7-1-1.7-2.1 0-1 .8-1.8 2-1.8.9 0 1.5.3 2 1.1l-1 .6c-.2-.4-.5-.6-.9-.6-.4 0-.7.3-.7.6 0 .4.3.6 1 .8l.4.2c1.2.5 1.8 1.1 1.8 2.2 0 1.2-.9 1.8-2.3 1.8Z" fill="#000" />
    </>
  ));
}

function NodeIcon({ size = 16, className, x, y }: LanguageIconProps) {
  return iconSvg(size, className, x, y, (
    <path d="M8 1.4 13.6 4.6v6.8L8 14.6 2.4 11.4V4.6L8 1.4Zm0 1.6L4 5.2v5.6l4 2.2 4-2.2V5.2L8 3Z" fill="#339933" />
  ));
}

function DotNetIcon({ size = 16, className, x, y }: LanguageIconProps) {
  return iconSvg(size, className, x, y, (
    <>
      <rect fill="#512BD4" height="14" rx="2" width="14" x="1" y="1" />
      <path d="M3.4 10.8V5.2h1.3l1.8 4.1h.1l1.8-4.1h1.3v5.6H8.5V7.2h-.1L6.9 10.8H6.2L4.7 7.2h-.1v3.6H3.4Zm8.2.2c-.9 0-1.5-.3-1.9-.8l.8-.6c.3.3.7.5 1.1.5.4 0 .6-.2.6-.4 0-.3-.2-.4-.8-.6l-.3-.1c-.9-.3-1.4-.8-1.4-1.6 0-.9.7-1.6 1.8-1.6.8 0 1.3.2 1.7.7l-.8.6c-.2-.3-.6-.4-.9-.4-.4 0-.6.2-.6.4 0 .3.2.4.8.6l.3.1c1 .3 1.5.8 1.5 1.7 0 1-.8 1.6-1.9 1.6Z" fill="#fff" />
    </>
  ));
}

function PhpIcon({ size = 16, className, x, y }: LanguageIconProps) {
  return iconSvg(size, className, x, y, (
    <>
      <rect fill="#777BB4" height="10" rx="5" width="14" x="1" y="3" />
      <path d="M4.6 6.2h1.6c.9 0 1.4.4 1.4 1.2 0 .9-.6 1.4-1.6 1.4H5.4L5.2 10H4.1l.5-3.8Zm1.1 1.8h.5c.4 0 .6-.2.6-.5 0-.3-.2-.5-.6-.5h-.4l-.1 1Zm3.2-1.8h1.1l-.5 3.8H8.4l.1-1H7.6l-.2 1H6.3l.5-3.8h1.1l-.1 1.1h.9l.2-1.1Zm.9 0h2.2l-.2 1.2h-1.1l-.1.8h1.1l-.2 1.1h-1.1l-.2 1.2h-1.1l.7-5.3Z" fill="#fff" />
    </>
  ));
}

function RubyIcon({ size = 16, className, x, y }: LanguageIconProps) {
  return iconSvg(size, className, x, y, (
    <path d="M8 14.4 1.8 8.2 4.4 2.2h7.2l2.6 6-6.2 6.2Z" fill="#CC342D" />
  ));
}

function RustIcon({ size = 16, className, x, y }: LanguageIconProps) {
  return iconSvg(size, className, x, y, (
    <>
      <circle cx="8" cy="8" fill="#DEA584" r="5.2" />
      <circle cx="8" cy="8" fill="none" r="3.2" stroke="#3D2C22" strokeWidth="1.2" />
      <circle cx="8" cy="8" fill="#3D2C22" r="1" />
    </>
  ));
}

function CppIcon({ size = 16, className, x, y }: LanguageIconProps) {
  return iconSvg(size, className, x, y, (
    <>
      <path d="M8 1.4 13.8 4.6v6.8L8 14.6 2.2 11.4V4.6L8 1.4Z" fill="#00599C" />
      <path d="M8.2 8.8V7.2h1.1v-.8H8.2V5.2h-.9v1.2H6.2v.8h1.1v1.6H6.2v.8h1.1V11h.9V9.6H9.3V8.8H8.2Zm2.4 0V7.2h1.1v-.8h-1.1V5.2h-.9v1.2h-1.1v.8h1.1v1.6h-1.1v.8h1.1V11h.9V9.6h1.1V8.8h-1.1Z" fill="#fff" />
    </>
  ));
}

function UnknownIcon({ size = 16, className, x, y }: LanguageIconProps) {
  return iconSvg(size, className, x, y, (
    <>
      <rect fill="var(--color-text-3)" height="5" rx="1" width="5" x="2" y="2" />
      <rect fill="var(--color-text-3)" height="5" rx="1" width="5" x="9" y="2" />
      <rect fill="var(--color-text-3)" height="5" rx="1" width="5" x="2" y="9" />
      <rect fill="var(--color-text-3)" height="5" rx="1" width="5" x="9" y="9" />
    </>
  ), 'default');
}

const LANGUAGE_ICONS: Record<string, (props: LanguageIconProps) => ReactNode> = {
  cpp: CppIcon,
  csharp: DotNetIcon,
  dotnet: DotNetIcon,
  go: GoIcon,
  golang: GoIcon,
  java: JavaIcon,
  javascript: JavaScriptIcon,
  js: JavaScriptIcon,
  node: NodeIcon,
  nodejs: NodeIcon,
  php: PhpIcon,
  python: PythonIcon,
  ruby: RubyIcon,
  rust: RustIcon,
};

export function hasKnownServiceLanguage(language?: string) {
  return Boolean(LANGUAGE_ICONS[normalizeServiceLanguage(language)]);
}

export default function ServiceLanguageIcon({
  language,
  size = 16,
  className,
  x,
  y,
}: LanguageIconProps & { language?: string }) {
  const Icon = LANGUAGE_ICONS[normalizeServiceLanguage(language)] ?? UnknownIcon;
  return <Icon className={className} size={size} x={x} y={y} />;
}
