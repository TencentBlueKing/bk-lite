# MLOps 训练数据文件生命周期

## 适用范围

六类使用 `TrainDataFileCleanupMixin` 的训练数据模型共享
`munchkin-public` 对象存储命名空间。数据库中的 `FileField` 路径是对象引用，
同一路径允许被同模型或不同训练数据模型的多条记录复用。

## 文件清理不变量

- 更新训练数据记录后，旧文件只在外层数据库事务提交后进入清理。
- 删除训练数据记录后也必须经过相同的全局引用检查，不得直接调用存储删除。
- 清理必须检查同一存储命名空间内的全部训练数据模型；任一已提交记录仍引用
  旧路径时不得删除对象。
- 文件路径的引用写入与“检查引用 → 删除对象”使用同一个数据库路径守卫串行化；
  守卫对相同路径全局生效，比存储命名空间边界更保守，防止命名空间无法可靠识别时
  检查完成后仍并发写入形成悬空引用。
- 清理先提交 `deleting` 栅栏，再持锁重查引用并执行对象删除，最后写入 `deleted`；
  删除或 tombstone 写入失败时保留 `deleting`，阻止旧字符串引用并允许任务安全重试。
- 已由清理流程删除的路径不能再次作为已有对象引用写入；重新上传并创建对象后
  方可重新激活该路径。
- 训练文件引用的新增或修改必须经过模型 `save()`；业务代码禁止用
  `QuerySet.update()`、`bulk_create()` 等绕过引用守卫的写法。
- 对象存储删除失败不得回滚已提交的业务记录，须由幂等 Celery 任务重查引用后重试。
- 六个训练数据路径字段保持数据库索引，避免跨模型引用检查退化为全表扫描。

## 实现证据

- `server/apps/mlops/models/mixins.py`
- `server/apps/mlops/models/train_data_file.py`
- `server/apps/mlops/services/train_data_file_cleanup.py`
- `server/apps/mlops/tasks/file_cleanup.py`
- `server/apps/mlops/tests/test_train_data_file_cleanup_mixin_service.py`
