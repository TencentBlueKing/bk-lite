#!/bin/bash

# webhookd mlops status script
# 接收 JSON: {"id": "train-001"} 或 {"ids": ["train-001", "train-002"]}

set -e

# 加载公共配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# 解析传入的 JSON 数据（第一个参数）
if [ -z "$1" ]; then
    json_error "INVALID_JSON" "" "No JSON data provided"
    exit 1
fi

JSON_DATA="$1"

# 提取参数（单个或多个）
set +e
SINGLE_ID=$(echo "$JSON_DATA" | jq -r '.id // empty' 2>/dev/null)
HAS_IDS=$(echo "$JSON_DATA" | jq -r 'if .ids then "true" else "false" end' 2>/dev/null)
set -e

# 构建容器 ID 数组
if [ -n "$SINGLE_ID" ] && [ "$SINGLE_ID" != "null" ]; then
    # 单个查询（向后兼容）
    IDS=("$SINGLE_ID")
elif [ "$HAS_IDS" = "true" ]; then
    # 批量查询
    set +e
    mapfile -t IDS < <(echo "$JSON_DATA" | jq -r '.ids[]' 2>/dev/null)
    set -e
    
    # 检查是否成功读取到数据
    if [ ${#IDS[@]} -eq 0 ]; then
        json_error "MISSING_REQUIRED_FIELD" "unknown" "Missing required field: id or ids"
        exit 1
    fi
else
    json_error "MISSING_REQUIRED_FIELD" "unknown" "Missing required field: id or ids"
    exit 1
fi

# ============ 关键优化：一次性 inspect 所有指定容器 ============
# 使用 docker inspect 批量查询（只查询指定的容器，不查询所有）
set +e
INSPECT_OUTPUT=$(docker inspect "${IDS[@]}" 2>&1)
INSPECT_STATUS=$?
set -e

# 构建结果数组
RESULTS="["
FIRST=true

if [ $INSPECT_STATUS -eq 0 ]; then
    # inspect 成功，解析每个容器的状态
    for container_id in "${IDS[@]}"; do
        # 从 inspect 输出中提取该容器的信息（禁用 set -e 防止 jq 失败）
        set +e
        CONTAINER_DATA=$(echo "$INSPECT_OUTPUT" | jq -r ".[] | select(.Name == \"/${container_id}\" or .Name == \"${container_id}\")" 2>/dev/null)
        set -e
        
        if [ -z "$CONTAINER_DATA" ]; then
            # 容器不存在（返回为合法状态）
            if [ "$FIRST" = false ]; then RESULTS="$RESULTS,"; fi
            RESULTS="$RESULTS{\"status\":\"success\",\"id\":\"$container_id\",\"state\":\"not_found\",\"port\":\"\",\"detail\":\"Container does not exist\"}"
            FIRST=false
            continue
        fi
        
        # 提取状态信息（禁用 set -e 防止 jq 失败）
        set +e
        STATE_STATUS=$(echo "$CONTAINER_DATA" | jq -r '.State.Status // "unknown"' 2>/dev/null)
        STATE_EXIT_CODE=$(echo "$CONTAINER_DATA" | jq -r '.State.ExitCode // 0' 2>/dev/null)
        STATE_STARTED_AT=$(echo "$CONTAINER_DATA" | jq -r '.State.StartedAt // ""' 2>/dev/null)
        STATE_FINISHED_AT=$(echo "$CONTAINER_DATA" | jq -r '.State.FinishedAt // ""' 2>/dev/null)
        STATE_ERROR=$(echo "$CONTAINER_DATA" | jq -r '.State.Error // ""' 2>/dev/null)
        
        # 从端口映射中提取宿主机端口（适配 -p 映射模式）
        # 如果是 host 网络模式，则从环境变量提取
        NETWORK_MODE=$(echo "$CONTAINER_DATA" | jq -r '.HostConfig.NetworkMode // ""' 2>/dev/null)
        if [ "$NETWORK_MODE" = "host" ]; then
            # host 网络模式：从环境变量提取
            PORT=$(echo "$CONTAINER_DATA" | jq -r '.Config.Env[]? | select(startswith("BENTOML_PORT=")) | split("=")[1] // ""' 2>/dev/null)
        else
            # 端口映射模式：提取宿主机端口
            PORT=$(echo "$CONTAINER_DATA" | jq -r '.NetworkSettings.Ports."3000/tcp"[0].HostPort // ""' 2>/dev/null)
        fi
        set -e
        
        # 判断状态
        case "$STATE_STATUS" in
            "running")
                STATUS="running"
                ;;
            "exited")
                if [ "$STATE_EXIT_CODE" = "0" ]; then
                    STATUS="completed"
                else
                    STATUS="failed"
                fi
                ;;
            *)
                STATUS="unknown"
                ;;
        esac
        
        # 构造 detail 信息
        if [ "$STATE_STATUS" = "running" ]; then
            # 计算运行时长
            if [ -n "$STATE_STARTED_AT" ] && [ "$STATE_STARTED_AT" != "0001-01-01T00:00:00Z" ]; then
                STARTED_TS=$(date -d "$STATE_STARTED_AT" +%s 2>/dev/null || echo "")
                if [ -n "$STARTED_TS" ]; then
                    CURRENT_TS=$(date +%s)
                    UPTIME_SECONDS=$((CURRENT_TS - STARTED_TS))
                    
                    # 格式化运行时长
                    if [ $UPTIME_SECONDS -ge 86400 ]; then
                        DAYS=$((UPTIME_SECONDS / 86400))
                        DETAIL="Up ${DAYS} days"
                    elif [ $UPTIME_SECONDS -ge 3600 ]; then
                        HOURS=$((UPTIME_SECONDS / 3600))
                        DETAIL="Up ${HOURS} hours"
                    elif [ $UPTIME_SECONDS -ge 60 ]; then
                        MINUTES=$((UPTIME_SECONDS / 60))
                        DETAIL="Up ${MINUTES} minutes"
                    else
                        DETAIL="Up ${UPTIME_SECONDS} seconds"
                    fi
                else
                    DETAIL="Up"
                fi
            else
                DETAIL="Up"
            fi
        else
            # 已停止的容器
            DETAIL="Exited ($STATE_EXIT_CODE)"
            
            # 添加退出时间信息
            if [ -n "$STATE_FINISHED_AT" ] && [ "$STATE_FINISHED_AT" != "0001-01-01T00:00:00Z" ]; then
                FINISHED_TS=$(date -d "$STATE_FINISHED_AT" +%s 2>/dev/null || echo "")
                if [ -n "$FINISHED_TS" ]; then
                    CURRENT_TS=$(date +%s)
                    STOPPED_SECONDS=$((CURRENT_TS - FINISHED_TS))
                    
                    # 格式化停止时长
                    if [ $STOPPED_SECONDS -ge 86400 ]; then
                        DAYS=$((STOPPED_SECONDS / 86400))
                        DETAIL="$DETAIL, stopped ${DAYS} days ago"
                    elif [ $STOPPED_SECONDS -ge 3600 ]; then
                        HOURS=$((STOPPED_SECONDS / 3600))
                        DETAIL="$DETAIL, stopped ${HOURS} hours ago"
                    elif [ $STOPPED_SECONDS -ge 60 ]; then
                        MINUTES=$((STOPPED_SECONDS / 60))
                        DETAIL="$DETAIL, stopped ${MINUTES} minutes ago"
                    else
                        DETAIL="$DETAIL, stopped ${STOPPED_SECONDS} seconds ago"
                    fi
                fi
            fi
            
            # 添加错误信息（如果有）
            if [ -n "$STATE_ERROR" ]; then
                DETAIL="$DETAIL, error: $STATE_ERROR"
            fi
        fi
        
        # 添加到结果
        if [ "$FIRST" = false ]; then RESULTS="$RESULTS,"; fi
        RESULTS="$RESULTS{\"status\":\"success\",\"id\":\"$container_id\",\"state\":\"$STATUS\",\"port\":\"$PORT\",\"detail\":\"$DETAIL\"}"
        FIRST=false
    done
else
    # inspect 失败，可能是部分容器不存在
    # 尝试逐个查询（兼容处理）
    for container_id in "${IDS[@]}"; do
        set +e
        CONTAINER_INFO=$(docker ps -a --filter "name=^${container_id}$" --format '{{.Status}}' 2>/dev/null)
        set -e
        
        if [ -z "$CONTAINER_INFO" ]; then
            # 容器不存在（返回为合法状态）
            if [ "$FIRST" = false ]; then RESULTS="$RESULTS,"; fi
            RESULTS="$RESULTS{\"status\":\"success\",\"id\":\"$container_id\",\"state\":\"not_found\",\"port\":\"\",\"detail\":\"Container does not exist\"}"
            FIRST=false
            continue
        fi
        
        # 判断状态（禁用 set -e 防止 grep 失败导致脚本退出）
        set +e
        if echo "$CONTAINER_INFO" | grep -q "Up"; then
            STATUS="running"
        elif echo "$CONTAINER_INFO" | grep -q "Exited (0)"; then
            STATUS="completed"
        elif echo "$CONTAINER_INFO" | grep -q "Exited"; then
            STATUS="failed"
        else
            STATUS="unknown"
        fi
        set -e
        
        # 从端口映射或环境变量提取端口（兼容处理分支）
        set +e
        NETWORK_MODE=$(docker inspect "$container_id" -f '{{.HostConfig.NetworkMode}}' 2>/dev/null || echo "")
        if [ "$NETWORK_MODE" = "host" ]; then
            # host 网络模式：从环境变量提取
            PORT=$(docker inspect "$container_id" -f '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep "BENTOML_PORT=" | cut -d= -f2 || echo "")
        else
            # 端口映射模式：提取宿主机端口
            PORT=$(docker inspect "$container_id" -f '{{(index (index .NetworkSettings.Ports \"3000/tcp\") 0).HostPort}}' 2>/dev/null || echo "")
        fi
        set -e
        
        # 添加到结果
        if [ "$FIRST" = false ]; then RESULTS="$RESULTS,"; fi
        RESULTS="$RESULTS{\"status\":\"success\",\"id\":\"$container_id\",\"state\":\"$STATUS\",\"port\":\"$PORT\",\"detail\":\"$CONTAINER_INFO\"}"
        FIRST=false
    done
fi

RESULTS="$RESULTS]"

# 返回结果（统一为数组格式）
echo "{\"status\":\"success\",\"results\":$RESULTS}"
exit 0
