/**
 * 资产模型图标目录的类型入口。
 * 实际数据在 model-icon-catalog.json；勿再内联巨型字符串映射，
 * 以免 CodeCC/semgrep 把图标名中的 `-p`/`-a` 误判为命令行密码。
 */
export { default } from './model-icon-catalog.json';
