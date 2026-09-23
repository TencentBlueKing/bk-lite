# CMDB 应用依赖产品决策记忆

- 最近更新：2026-09-18
- 当前规格：`specs/changes/cmdb-application-connect-dependency/spec.md`

## 产品定位

应用依赖是应用与数据库/中间件/云上同类之间的消费关系。它不是服务树节点，也不是主机上的进程落点。

## 已确认范围

- 应用模型预置 `connect` n:n 到服务身份模型。
- 实例关联页手工建/拆边；应用拓扑按跳数带出。
- 第一期只改模型种子，不改服务树、不自动发现。

## 已确认设计决策

- 用已有 `connect`，不新增「访问」。`contains` 会变成组织树，`run` 表示进程落点。
- 基数 n:n：一套库服务多个应用，一个应用连多套库。
- 只接到主模型（MySQL、Oracle、Redis、Kafka、Nacos、云 RDS 等）。不接 Tomcat/Nginx/HAProxy，不接 PDB/租户/节点/通道。
- 同机两跳推断（方案一）保留；本变更只补消费边（方案二）。

## 明确后置

- 扫描或同主机自动建消费边。
- 依赖反查报表或专用管理页。
- 大数据组件（HDFS/YARN/Storm/Ambari/Spark）和应用运行载体。

## 仍待确认

无。

## 已替代决策

无。

## 决策来源

- 用户于 2026-09-18 确认方案二：connect n:n、服务身份模型、第一期只做种子。
- `specs/changes/cmdb-application-connect-dependency/spec.md`
