## 1. 代码修复

- [x] 1.1 修改 `agents/ansible-executor/service/ansible_runner.py` 第 759 行，将 `zf.extractall(workspace)` 替换为 `_safe_extract_zip(zf, workspace)`

## 2. 验证

- [x] 2.1 运行 `cd agents/ansible-executor && make lint` 确保代码风格通过
- [x] 2.2 运行现有测试 `test_ansible_runner.py` 确保安全函数测试通过
- [x] 2.3 手动验证：确认修改后的代码路径与 file_distribution 路径（Line 785）使用相同的安全函数
