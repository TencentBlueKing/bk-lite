# 日志提取器 Grok 类型产品决策记忆

- 最近更新：2026-11-16
- 当前规格：`specs/changes/log-extractor-grok/spec.md`（implemented，2026-11-16）；基线为 `specs/changes/log-file-extractor/spec.md`、`specs/changes/log-extractor-passive-collect/spec.md`

## 产品定位

Grok 是日志提取器的第七种提取类型，目标是降低「从文本中抽字段」的配置门槛：用户用 `%{NUMBER:http.status}` 这类内置模式名写规则，不必手写命名捕获组和映射 JSON。不以「客户现成 Logstash / ELK Grok 规则原样迁移」为第一版目标。

## 已确认范围

- 新增提取类型 `grok`，与现有六类并列；实例提取器与 syslog / snmptrap 类型级提取器共用，条件、顺序执行、失败隔离、全局发布与权限沿用现状。
- 执行端仍是中心系统 Vector，不改 fusion-collector / 采集侧 Vector。

## 已确认设计决策

- 不使用 Vector 原生 `parse_grok` / `parse_groks`。由服务端维护 BK-Lite 模式库，把 Grok 展开为 Rust regex 兼容的正则，复用现有 `regex` 的执行与 `parse_regex` 编译。原因：
  - Vector 0.48 所带 VRL 0.25.0 依赖 `grok = "2.1"` 默认特性，即 Oniguruma 回溯引擎；中心 Vector 是全租户共享管道，正文最大约 10 MiB 且运行时无单条正则超时，一条回溯型规则可拖慢全部日志入库。现有正则类型刻意限定 Rust regex（线性匹配）。
  - 原生 Grok 需要 Python 预览模拟 Oniguruma 语义，难以满足「预览与 Vector 0.48 同批样例一致」的既有契约。
- 接受与 Logstash Grok 的个别差异（例如 IP 以 `\b` 边界代替前后查找）；模式库每个模式都必须进入 Python 预览与 Vector 0.48 同批契约样例，对不上的模式不收录。

## 已确认规则细节（2026-11-16 用户批准规格）

- `%{模式名:属性路径}` 的冒号后即目标属性路径（普通段点分，允许嵌套），Grok 类型不提供捕获组映射；输出路径不可重复、不可互为祖先、不可以保护字段为根或写 `message`。
- 不支持第三段类型过滤器，输出全为字符串，保存时明确拒绝。复合模式不能再命名（与阿里云 SLS 一致）。
- 字面量按正则处理（兼容 Logstash / SLS 写法），通过与 `regex` 相同的 Vector 兼容性校验；字面量内不允许命名捕获组。匹配不锚定，与正则提取一致。
- 限制：原文 1–2000 字符，展开后 ≤16384 字符，引用 ≤64 个。
- 模式名沿用 Logstash / Elastic / SLS 经典名称，第一版约 50 个原子模式加 `COMMONAPACHELOG`、`COMBINEDAPACHELOG`（含 Nginx combined）、`SYSLOGBASE` 三个复合模式。复合输出采用 ECS 风格字段名；行内时间统一写 `log_time` 字符串，不碰 `timestamp`。
- 模式库只追加；修改已有定义须补回归样例、递增中心 Vector 配置契约版本并重新发布。
- 新增只读模式目录接口供前端插入面板使用，不在前端复制清单；不经 OpenAPI 网关。
- 预览纳入现有正则隔离执行（子进程、超时、并发上限）。

## 明确后置

- 自定义别名、多模式择一、类型转换过滤器。
- 原样兼容 Logstash / ELK Grok 规则迁移（需要原生引擎与中心 Vector 性能隔离）。
- 搜索页选中文本反推 Grok（沿用 `log-extractor-passive-collect.md` 的后置决定）。

## 仍待确认

无

## 已替代决策

- 2026-11-16：初版建议「Grok 编译为 Vector 原生 `parse_grok`、仅内置模式名、复用 `group_mapping`」被替代，原因见上方「已确认设计决策」。

## 决策来源

- 需求：日志中心新增 Grok 模式，降低日志字段提取的配置门槛。
- 用户确认（2026-11-16）：第一版首要目标是降低配置门槛，可接受与 Logstash 的个别差异，采用自维护模式库展开为 `parse_regex`。
- 用户要求（2026-11-16）：结合项目现状与竞品先出一版最推荐方案；随后批准 `specs/changes/log-extractor-grok/spec.md` 并要求实施。
- 竞品参照：阿里云 SLS `grok()` 展开为正则交 `e_regex`；Graylog 从消息创建 Grok 提取器并测试、仅命名捕获；Elastic ingest `pattern_definitions` / ECS 字段名；Datadog 辅助规则与样本匹配状态；Loki `pattern` 占位符解析器。
- 外部事实：vectordotdev/vrl v0.25.0 `Cargo.toml`（`grok = { version = "2.1" }`）、`src/stdlib/parse_grok.rs`、`parse_groks.rs`；grok crate 2.1.0 默认特性为 `onig`。
