# 最新上游适配与验证记录（2026-10-30）

## 实施结果

基于刷新后的 TencentBlueKing/bk-lite master `7fc417be88`。仅将原默认worker拆成critical、notification、state、background四池，保留OpsPilot、报表、补丁维护既有专用消费者、原生prefork、任务软硬超时、200任务/512000KiB默认回收及ACK/retry。

最新静态清单182项，准确处理显式name及queue；截图中的导出、批量关联、节点收敛等任务已找到源码。四池MAX、既有专用并发、所有同构副本及升级重叠纳入同一总预算；完整安装7个worker主进程，容量必须实测，不提供并发1够用的承诺。

默认worker/Beat由公共解析器生成，保留上游migrate失败门禁、batch_init和可选进程清理；生成前使用与实际专用消费者一致的shell导出配置。管理命令只读注册不触发周期表同步；ORM路由工具默认dry-run、显式ID名单、快照与冲突恢复。业务任务函数、模型、周期未修改。

## 新鲜验证

| 项目 | 结果 |
|---|---|
| TDD | 先验证旧兼容池取消超时、预算遗漏专用池、旧路由清单、项目日志规范的失败，再适配修复 |
| 公共配置/路由/观测/诊断/ORM/启动及上游Beat同步 | 110 passed；独立Django/Beat SQLite环境，未加载全部业务应用 |
| 覆盖率 | 91.85%（810语句、66未覆盖），范围为公共runtime、core.celery、Celery配置和两个管理命令；不是全仓覆盖率 |
| 真实Redis / prefork | 5 passed（32.51秒）：隔离、扩缩容、ETA/重试/历史队列、原生软硬超时、任务数阈值回收 |
| 格式/静态 | 触及文件black/isort/flake8、bash语法、diff空白及OpenSpec strict校验通过；仓库pre-commit全部通过 |
| 平台边界 | 本机macOS专用探针显式fork，不能替代目标Linux镜像的全应用验证；不连接生产broker、不投递真实业务或远端作业 |

## 未完成的发布门槛

- `cd server && make test` 实际执行，仍在MLOps初始化因缺少可选依赖mlflow失败；没有隐藏业务测试或修改业务代码绕过。
- 本机Docker此前拉镜像返回containerd元数据I/O错误；未重置Docker，目标Linux测试仍待完成。
- 生产commit、启用模块、副本数、实际注册/生产者/持久化Beat路由仍需现场核对；当前源码不是生产状态证明。
- 16–32GB全组件同时MAX峰值、升级重叠、真实任务排队分位数和积压排空/回滚演练尚未执行。回收阈值不是单任务硬内存上限。

当前交付为经过审查和本地验证的草稿PR，尚未达到生产发布或OpenSpec归档条件。没有部署生产、清空消息、批量重投或修改业务调度。

## 单实例默认配置补充（2026-11-04）

根据用户要求，启用Celery时缺失的新参数使用固定默认值：critical/notification/state为MIN=1、MAX=2，background为MIN=MAX=1，总并发上限12（含既有专用池默认2+2+1）。环境变量逐项覆盖；显式空值、非法值及超预算仍拒绝。旧CELERY_CONCURRENCY提示废弃并忽略，不复制到各池。默认预算不随覆盖值或副本数自动放大；默认值不是生产容量验收结果。

TDD先得到5项预期失败，再实现默认值。使用独立Python3.12环境、Celery5.4.0、Django4.2.27验证：

- 原110项相关测试范围更新后共116项通过（`DJANGO_SETTINGS_MODULE=apps.core.tests.celery_test_settings python -m pytest --noconftest -c /dev/null`，10个相关测试文件）；`--cov=apps.core.celery_runtime.config --cov-fail-under=75`结果为76语句、100%。新增覆盖默认启动、部分覆盖、旧变量忽略、固定总预算拒绝超额及模板一致性。
- `CELERY_RUNTIME_INTEGRATION=1 python -m pytest --noconftest -c /dev/null -p no:django apps/core/tests/test_celery_runtime_integration.py -q`：5 passed，32.47秒。四池使用产品默认范围和预算，测试仅覆盖收缩等待为2秒，仍为本机macOS专用探针。
- 4个触及Python文件black/isort/flake8检查通过；OpenSpec strict和diff检查通过。
- `UV_PROJECT_ENVIRONMENT=/tmp/pr6882-review-20261104-venv UV_NO_SYNC=1 make test`已尝试，在Django初始化时因临时环境缺少rest_framework退出，未进入全量测试。该环境只安装公共runtime测试依赖，不代表全应用门禁已通过。

本次仅消除新配置缺失及旧并发变量导致的启动阻塞。目标Linux、生产路由、整机容量、迁移与回滚待办保持未完成；没有更新远端PR或部署。

## Linux运行层与迁移回滚验收（2026-11-04）

### 环境及范围

默认Docker实例存在containerd元数据I/O错误，未重置它。使用另一个可用实例中的独立临时容器，无外部网络，不挂载生产数据；内存上限1.5GiB、CPU上限1.5、进程上限160，Redis和PostgreSQL均在容器内部临时创建。

Docker宿主为ARM64，测试容器为AMD64仿真环境：Linux6.8.0-50、Debian12/glibc2.36、Python3.12.10、Celery5.4.0、Kombu5.6.2、redis-py5.0.1、Redis8.2.3、PostgreSQL15.19。使用现有诊断镜像`sha256:3d991eee86870207744938a41e7c628f970423e46cf0c3b7904222d50b913b8d`和独立Python发行包。正式server-base没有ARM64清单，AMD64拉取持续超时；本次没有构建或运行完整发行镜像，也未加载全部业务应用。

### 实际发现及修复

- **生产依赖不兼容**：Celery5.4未约束Kombu次版本，解析到5.7后，Redis传输抛出`VersionMismatch`，要求redis-py≥6.1，而项目固定5.0.1。真实Redis测试因此得到5项错误、3项失败。生产`pyproject.toml`与独立测试清单统一锁定Kombu5.6.2；其[官方包元数据](https://pypi.org/pypi/kombu/5.6.2/json)声明的Redis额外依赖允许5.0.1，下载wheel核对SHA256后再完整验证。
- **巡检探针不稳定**：消息均已完成，但0.5秒广播巡检不能稳定确认所有worker排空。改为定向检查全部存活节点，等待2秒回复，缺失回复仍失败；失败摘要仅记录节点、各阶段计数及ready，不记录任务参数。单独回滚探针及最后完整验收均通过。
- 准备阶段发现独立容器缺少make/模板、子进程不能继承独立依赖目录，以及Python安装器的受管理环境保护；只修正临时容器准备方式，未修改业务代码绕过测试。保留准备和失败轮次日志。

### 最后完整执行

容器内设置独立测试库端口55432、`COVERAGE_FILE=/evidence/.coverage`后，执行：

```bash
bash scripts/check_celery_runtime.sh /evidence
```

| 验收范围 | 结果 |
|---|---|
| 默认配置、路由、观测、诊断、命令、真实PostgreSQL ORM/Beat路由恢复及发布启动契约 | 117 passed，0错误/失败/跳过，21.73秒 |
| Redis四池隔离、伸缩、历史队列、ETA/重试、软硬超时及子进程回收 | 5 passed |
| 旧积压+在途任务迁移、仅回退默认worker导致滞留的复现与接管、多队列+ETA+重试回滚 | 3 passed |
| 合计真实Redis探针 | 8 passed，0错误/失败/跳过，97.46秒 |
| 运行层覆盖率 | 92.61%（379语句、28未覆盖）；配置解析器100%，不是全仓覆盖率 |

迁移演练在新消费者就绪后混合投递新旧路由，对旧worker发送TERM并确认等待受控在途任务释放，后台池排空旧队列。回滚演练先核对回退worker注册集、接管五个队列，再温和关闭新四池；未来ETA和重试保留原任务ID，ETA未提前，重试次数为1；核对探针执行次数，并检查全部存活节点的active/reserved/scheduled与五队列ready均为空。没有purge、批量重投或强杀在途任务。

Beat路由命令在真实PostgreSQL上验证dry-run、排他0600快照、应用、恢复预览/应用及冲突拒绝，业务参数、周期、名称和启停保持不变。没有启动生产Beat，不把该测试视为部署唯一性证明。

原始环境、源码SHA256、JUnit、worker日志和失败轮次保存在本机`/tmp/bklite-celery-linux-evidence-20261104/`。容器生命周期cgroup内存峰值926.12MiB（包含准备和失败重试），这不是全组件或真实业务容量结论。证据导出后停止临时PostgreSQL并删除本次容器及其匿名卷，未影响既有服务。

已增加`server/scripts/check_celery_runtime.sh`、最小依赖清单、临时PostgreSQL设置和`.github/workflows/server-celery-runtime-check.yml`；CI尚未推送或远端执行。black/isort/flake8、requirements检查、bash语法及OpenSpec strict通过。再次执行全量`make test`仍在临时环境因缺少rest_framework失败，未进入全量业务测试。

已完成独立Linux运行层和拓扑/协议迁移回滚验收。生产版本与显式路由核对、完整业务镜像/真实旧版本兼容性、全组件容量和30分钟/1000探针时延目标、唯一Beat部署切换仍未验收；相应待办不勾选，不据此宣称可直接上线。

## 合入前全量CI（2026-11-04）

提交`5b5b75c417`已推送PR #6882，远端原生Linux专项、导入、迁移及其他既有检查通过。新增完整依赖的`full-server`执行真实`make test`，发现8个收集错误：内嵌PPT工具与Django均使用顶层`config`模块，PPT测试错误导入`server/config`，并非Celery业务断言失败。结果见Actions运行`41792433550`、作业`126448678063`。

针对这一运行边界，将`make test`改为两套独立pytest子进程：应用侧仅分离精确的PPT `scripts/tests`路径；PPT侧在脚本目录收集全部57个文件，不加载Django插件、配置和父级conftest。没有删除或跳过这套745个静态测试方法；两套均生成JUnit，任一失败则门禁失败，首套失败仍执行第二套。直接pytest及app/marker快捷命令仅代表应用套件，完整门禁入口已在测试指南更新。

先写进程隔离行为回归并观察缺少入口的失败，再实现最小编排器：使用同名config与应用autouse fixture的临时工程，验证两套都实际收集并通过，以及任意一套失败均传递非零退出码。3项回归通过，新增编排器覆盖率90.91%。最终完整业务结果仍以更新后的远端CI为准，不将专项通过或测试收集修复报告为全量通过。

第二轮CI（`41795468035`）实际执行PPT套件：735 passed、7 failed、3 skipped。应用收集暴露通用`scripts`命名空间冲突，编排器迁入唯一的`apps.core.testing_runner`，入口改为`python -m apps.core.testing_runner`，importlib模式下的3项回归仍通过、覆盖率90.91%。

PPT七项失败逐一处理，未删除测试或放宽安全断言：

- 四项音频测试缺少ffprobe/ffmpeg，在CI安装系统工具。
- TLS测试替身使用SimpleNamespace，而当前urllib3对结果进行解包；替身改为同时保留属性与可解包形状的namedtuple，Host/IP/端口/SNI/CERT_REQUIRED/assert_hostname断言均保留，生产HTTP传输实现未改。
- 两项页面/前端行为测试暴露旧版本漏包：`server/.gitignore`的裸`static`规则误忽略了内嵌工具资源。恢复官方[v6.7.2固定提交](https://github.com/hugohe3/ppt-master/tree/b113d23720260c411ee47b2b05a73615f954deeb)的原始资源，未从main获取新版本。已核对SKILL.md、三个服务端模块和相关两个测试的Git blob与仓库基线一致。

仅恢复confirm_ui/static、svg_editor/static、spec_review/static三个目录，共28文件、581924字节，每文件与源Git blob核验一致；三个原始tree依次为`0e0fbd66f0137df4fda9536ae2ebf8b57c28e532`、`0a44cf30ecd3112ec38aa83acf5c332cb4b086e7`、`189865c2df52148effd1fa60bdf0d8eb2a6b6c86`。只为这三处添加精确gitignore例外，Django生成的static仍被忽略。

本地七项针对性回归全部通过（Mac使用规范化TMPDIR=/private/tmp，避免/var与/private/var别名影响路径校验）；资源集合及逐blob复核通过。一次本地全PPT尝试因最小环境缺PyMuPDF而停止，未报告为完整通过；远端完整依赖下仍执行全部PPT测试。规范/规格复核未发现新增代码阻断，完整门禁以最终提交的远端结果为准。

第三轮CI（`41799128130`，提交`3e6e86f7e2`）：原生Linux专项、导入、迁移和代码安全扫描通过；PPT完整套件为742 passed、3 skipped。应用套件实际执行至160 passed、5 skipped、1 failed后停止：既有告警责任人端到端测试以`fp-{event.event_id}`构造超32字符指纹，触发PostgreSQL租约表字段长度限制。已核对目标基线`7fc417be`同一测试输入；改用项目现有32位指纹生成器，保留三个owner结果及三个operator结果断言，不调整生产字段或分派代码。

全量CI的失败收集上限从1增至10，仍有任一失败即整体失败；新增120秒慢用例线程栈输出，并将作业时限调整为60分钟，以收集后续阻塞证据。上述测试输入修复的执行结果以新提交CI为准，尚不宣称全量通过。
