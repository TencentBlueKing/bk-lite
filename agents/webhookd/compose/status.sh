#!/bin/bash

# webhookd compose status script
# 接收参数: id (通过 URL 参数或 JSON)
# 支持单个 id 或 id 数组: {"id": "app-001"} 或 {"ids": ["app-001", "app-002"]}

# 加载公共配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# 获取单个服务的状态
get_single_status() {
    local id="$1"
    local compose_path="$COMPOSE_DIR/$id"
    
    if [ ! -d "$compose_path" ]; then
        echo "{\"id\":\"$id\",\"status\":\"error\",\"message\":\"Compose directory not found\"}"
        return
    fi
    
    cd "$compose_path"
    local containers=$(docker-compose ps --format json 2>&1)
    local result=$?
    
    if [ $result -eq 0 ]; then
        # docker-compose ps --format json 返回多行 JSON，需要转换为数组
        # 移除空白字符后检查是否为空
        local trimmed=$(echo "$containers" | tr -d '[:space:]')
        if [ -z "$trimmed" ]; then
            echo "{\"id\":\"$id\",\"status\":\"success\",\"containers\":[]}"
        else
            # 过滤掉冗长的字段(如 Labels),只保留关键信息,避免 webhookd 输出截断
            local containers_array=$(echo "$containers" | jq -s '[.[] | {Name, State, Status, Service, Image, Ports, Size, ID: .ID[0:12]}]' 2>/dev/null)
            # 检查 jq 是否成功执行
            if [ $? -eq 0 ] && [ -n "$containers_array" ]; then
                echo "{\"id\":\"$id\",\"status\":\"success\",\"containers\":$containers_array}"
            else
                # jq 失败时返回空数组
                echo "{\"id\":\"$id\",\"status\":\"success\",\"containers\":[]}"
            fi
        fi
    else
        local error=$(echo "$containers" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | tr '\n' ' ')
        echo "{\"id\":\"$id\",\"status\":\"error\",\"message\":\"Failed to get status\",\"error\":\"$error\"}"
    fi
}

# 获取 ID 或 IDs
if [ -n "$id" ]; then
    # URL 参数传入单个 ID
    ID="$id"
elif [ -n "$1" ]; then
    # JSON 数据
    JSON_DATA="$1"
    
    # 尝试解析 ids 数组
    IDS=$(echo "$JSON_DATA" | jq -r '.ids[]? // empty' 2>/dev/null)
    
    if [ -z "$IDS" ]; then
        # 如果没有 ids 数组，尝试解析单个 id
        ID=$(echo "$JSON_DATA" | jq -r '.id // empty' 2>/dev/null)
    fi
fi

# 处理多个 ID
if [ -n "$IDS" ]; then
    RESULTS="["
    FIRST=true
    
    while IFS= read -r service_id; do
        if [ -n "$service_id" ]; then
            if [ "$FIRST" = true ]; then
                FIRST=false
            else
                RESULTS="$RESULTS,"
            fi
            STATUS_RESULT=$(get_single_status "$service_id")
            RESULTS="$RESULTS$STATUS_RESULT"
        fi
    done <<< "$IDS"
    
    RESULTS="$RESULTS]"
    echo "{\"status\":\"success\",\"data\":$RESULTS}"
    exit 0
fi

# 处理单个 ID
if [ -n "$ID" ]; then
    COMPOSE_PATH="$COMPOSE_DIR/$ID"
    if [ ! -d "$COMPOSE_PATH" ]; then
        echo "{\"id\":\"$ID\",\"status\":\"error\",\"message\":\"Compose directory not found\"}"
        exit 1
    fi
    
    cd "$COMPOSE_PATH"
    STATUS_OUTPUT=$(docker-compose ps --format json 2>&1)
    STATUS_RESULT=$?
    
    if [ $STATUS_RESULT -eq 0 ]; then
        # docker-compose ps --format json 返回多行 JSON，需要转换为数组
        # 移除空白字符后检查是否为空
        TRIMMED=$(echo "$STATUS_OUTPUT" | tr -d '[:space:]')
        if [ -z "$TRIMMED" ]; then
            echo "{\"id\":\"$ID\",\"status\":\"success\",\"containers\":[]}"
        else
            # 过滤掉冗长的字段(如 Labels),只保留关键信息,避免 webhookd 输出截断
            CONTAINERS_ARRAY=$(echo "$STATUS_OUTPUT" | jq -s '[.[] | {Name, State, Status, Service, Image, Ports, Size, ID: .ID[0:12]}]' 2>/dev/null)
            # 检查 jq 是否成功执行
            if [ $? -eq 0 ] && [ -n "$CONTAINERS_ARRAY" ]; then
                echo "{\"id\":\"$ID\",\"status\":\"success\",\"containers\":$CONTAINERS_ARRAY}"
            else
                # jq 失败时返回空数组
                echo "{\"id\":\"$ID\",\"status\":\"success\",\"containers\":[]}"
            fi
        fi
    else
        ERROR=$(echo "$STATUS_OUTPUT" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | tr '\n' ' ')
        echo "{\"id\":\"$ID\",\"status\":\"error\",\"message\":\"Failed to get status\",\"error\":\"$ERROR\"}"
    fi
    exit 0
fi

# 如果没有提供任何 ID，查询所有服务的详细状态
if [ -d "$COMPOSE_DIR" ]; then
    ALL_IDS=$(ls -1 "$COMPOSE_DIR" 2>/dev/null)
    
    if [ -z "$ALL_IDS" ]; then
        echo "{\"status\":\"success\",\"data\":[]}"
        exit 0
    fi
    
    RESULTS="["
    FIRST=true
    
    while IFS= read -r service_id; do
        if [ -n "$service_id" ]; then
            if [ "$FIRST" = true ]; then
                FIRST=false
            else
                RESULTS="$RESULTS,"
            fi
            STATUS_RESULT=$(get_single_status "$service_id")
            RESULTS="$RESULTS$STATUS_RESULT"
        fi
    done <<< "$ALL_IDS"
    
    RESULTS="$RESULTS]"
    echo "{\"status\":\"success\",\"data\":$RESULTS}"
else
    echo "{\"status\":\"success\",\"data\":[]}"
fi
exit 0
