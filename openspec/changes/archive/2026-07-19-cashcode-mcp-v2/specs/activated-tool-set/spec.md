## ADDED Requirements

### Requirement: ActivatedToolSet 是 LRU 激活集
`ActivatedToolSet` SHALL 以 `{tool_name: timestamp}` 的 `OrderedDict` 存储已激活工具，容量上限50，超出时 evict 最旧条目，`visibility_revision` 在成员变化时递增。

#### Scenario: activate 新工具
- **WHEN** 调用 `activated_set.activate("mcp_weather_get_weather")`，工具不在集合中
- **THEN** 工具加入集合，`visibility_revision += 1`，`is_activated("mcp_weather_get_weather")` 返回 True

#### Scenario: activate 已有工具只更新时间戳
- **WHEN** 调用 `activate("mcp_weather_get_weather")`，工具已在集合中
- **THEN** 时间戳更新，`visibility_revision` 不变，集合长度不变

#### Scenario: 超出容量时 evict 最旧
- **WHEN** 集合已有50个工具，再 activate 第51个新工具
- **THEN** 时间戳最旧的工具被移除，新工具加入，集合长度仍为50

### Requirement: ActivatedToolSet 直接持有 metadata 子dict引用
`ActivatedToolSet.from_session(metadata_dict)` SHALL 直接使用 `metadata_dict.setdefault("activated_tools", {})` 的引用（非拷贝），对 `_raw` 的写入立即反映到 metadata dict 中。

#### Scenario: activate 后 metadata 立即更新
- **WHEN** 通过 `from_session(metadata)` 创建集合后调用 `activate("mcp_tool")`
- **THEN** `metadata["activated_tools"]["mcp_tool"]` 存在且为 float 时间戳

### Requirement: ActivatedToolSet 绑定到当前 async task
`use_activated_set(activated_set)` ContextVar 上下文管理器 SHALL 将激活集绑定到当前 async task，`get_activated_set()` 返回当前绑定的集合或 None。

#### Scenario: 每轮对话开始时绑定
- **WHEN** `_handle_turn()` 开始处理
- **THEN** 通过 `use_activated_set(set)` 绑定当前 chat_id 的激活集，runner 和 tool_search 均可通过 `get_activated_set()` 读取
