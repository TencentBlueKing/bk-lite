# 同步所有语言包
sync-all:
	uv run lang-syncer.py push_web_pack
	uv run lang-syncer.py sync_web_pack
	uv run lang-syncer.py push_server_pack
	uv run lang-syncer.py sync_server_pack

# Web 前端语言包同步
push-web:
	uv run lang-syncer.py push_web_pack

sync-web:
	uv run lang-syncer.py sync_web_pack

# Server 后端语言包同步
push-server:
	uv run lang-syncer.py push_server_pack

sync-server:
	uv run lang-syncer.py sync_server_pack

# 安装依赖
install:
	uv sync

# 清理缓存
clean:
	rm -rf __pycache__ src/lang_syncer/__pycache__ .pytest_cache
	find . -type d -name "*.egg-info" -exec rm -rf {} +

.PHONY: sync-all push-web sync-web push-server sync-server install clean