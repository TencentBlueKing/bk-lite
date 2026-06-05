# language: zh-CN
功能: 运营分析目录树
  作为运营分析平台
  为了让画布按层级目录组织
  Directory 模型必须维护 ≤3 层层级、name+parent 联合唯一、build_in_key 唯一、子目录级联

  # ---------- Happy Path ----------

  场景: 正常路径 - 创建根目录
    当 我创建目录 name="根" parent=None groups=[1]
    那么 目录创建应当成功
    并且 目录 "根" 的层级应当为 0

  场景: 正常路径 - 在根下创建二级子目录
    假设 已存在目录 "根" 无父目录 groups=[1]
    当 我创建目录 name="子1" parent="根" groups=[1]
    那么 目录创建应当成功
    并且 目录 "子1" 的层级应当为 1

  # ---------- Corner Case ----------

  场景: 边界 - 同 parent 下 name 联合唯一
    假设 已存在目录 "根" 无父目录 groups=[1]
    并且 已存在目录 "子1" parent="根" groups=[1]
    当 我尝试创建目录 name="子1" parent="根" groups=[1]
    那么 应当抛出唯一约束异常

  场景: 边界 - 不同 parent 下允许同名
    假设 已存在目录 "根A" 无父目录 groups=[1]
    并且 已存在目录 "根B" 无父目录 groups=[1]
    当 我创建目录 name="同名" parent="根A" groups=[1]
    并且 我创建目录 name="同名" parent="根B" groups=[1]
    那么 目录创建应当成功

  场景: 边界 - 层级超过 3 层时被拒
    假设 已存在目录 "L0" 无父目录 groups=[1]
    并且 已存在目录 "L1" parent="L0" groups=[1]
    并且 已存在目录 "L2" parent="L1" groups=[1]
    当 我尝试创建目录 name="L3" parent="L2" groups=[1]
    那么 应当抛出层级超限异常

  场景: 边界 - 删除父目录级联删除所有子目录
    假设 已存在目录 "根" 无父目录 groups=[1]
    并且 已存在目录 "子1" parent="根" groups=[1]
    当 我删除目录 "根"
    那么 数据库中不应再存在目录 "子1"

  场景: 边界 - 内置目录 build_in_key 唯一约束
    假设 已存在内置目录 name="builtin_dir1" build_in_key="bk_root" groups=[1]
    当 我尝试创建内置目录 name="builtin_dir2" build_in_key="bk_root" groups=[1]
    那么 应当抛出唯一约束异常
