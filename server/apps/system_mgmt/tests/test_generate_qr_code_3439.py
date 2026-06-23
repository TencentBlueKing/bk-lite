"""
Issue #3439: generate_qr_code NATS handler 无调用方鉴权，可对任意用户重置 OTP secret

验证：
1. 不安全的 generate_qr_code(username) NATS handler 已从注册表中移除
2. 安全替代接口 generate_qr_code_by_user_id 仍正常注册并可用
3. rpc/system_mgmt.SystemMgmtClient 不再暴露 generate_qr_code(username) 方法

回归准则：若将修复 revert（还原已删除的 generate_qr_code handler），
test_insecure_handler_removed 必然失败。
"""

import pytest


class TestGenerateQrCode3439:
    """Issue #3439 安全修复验证"""

    def test_insecure_handler_removed(self):
        """
        generate_qr_code(username) NATS handler 必须已从注册表中移除。

        该接口接受外部传入的 username，无任何调用方身份校验，
        任意内网服务可通过单条 NATS 消息覆盖任意用户的 OTP secret。

        若此测试失败，说明不安全 handler 仍在注册表中，需立即处理。
        """
        import nats_client as nc

        registry = nc.default_registry.registry

        # 所有注册的 key 中不应存在 "generate_qr_code" 但不含 "_by_user_id" 的条目
        insecure_keys = [
            key for key in registry
            if "generate_qr_code" in key and "by_user_id" not in key
        ]
        assert insecure_keys == [], (
            f"不安全的 generate_qr_code NATS handler 仍在注册表中: {insecure_keys}。"
            "该接口无调用方鉴权，已于 Issue #3439 废弃，请确认修复已生效。"
        )

    def test_secure_handler_still_registered(self):
        """
        generate_qr_code_by_user_id NATS handler 必须仍在注册表中（安全替代接口）。
        """
        import nats_client as nc

        registry = nc.default_registry.registry

        secure_keys = [key for key in registry if "generate_qr_code_by_user_id" in key]
        assert len(secure_keys) >= 1, (
            "generate_qr_code_by_user_id NATS handler 未找到，安全替代接口异常缺失。"
        )

    def test_rpc_client_does_not_expose_insecure_method(self):
        """
        SystemMgmtClient RPC 包装类不应再暴露 generate_qr_code(username) 方法。

        若 RPC 方法仍存在，调用方可能误用绕过鉴权。
        """
        from apps.rpc.system_mgmt import SystemMgmtClient

        assert not hasattr(SystemMgmtClient, "generate_qr_code"), (
            "SystemMgmtClient 仍暴露 generate_qr_code(username) 方法，"
            "该方法对应已废弃的不安全 NATS handler，应随 Issue #3439 一并移除。"
        )

    def test_rpc_client_secure_method_exists(self):
        """
        SystemMgmtClient 必须保留 generate_qr_code_by_user_id 方法（安全替代接口）。
        """
        from apps.rpc.system_mgmt import SystemMgmtClient

        assert hasattr(SystemMgmtClient, "generate_qr_code_by_user_id"), (
            "SystemMgmtClient 缺少 generate_qr_code_by_user_id 方法，安全替代接口异常缺失。"
        )
