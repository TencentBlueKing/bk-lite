import zh from './zh.json';
import en from './en.json';
let locale = 'zh';
export const setContentLocale = (value: string) => { locale = value; };
export const getOpspilotTranslate = () => (key: string, fallback = key, values?: Record<string, string | number>) => {
  const catalog: Record<string, string> = locale === 'en' ? en : zh;
  return (catalog[key] || fallback).replace(/\{(\w+)\}/g, (match, name) => values?.[name] == null ? match : String(values[name]));
};
