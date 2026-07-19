## MODIFIED Requirements

### Requirement: Detect oversized context and trigger consolidation
`SimpleConsolidator.maybe_consolidate` SHALL 接受 `last_consolidated: int = 0` 参数，仅对 `history[last_consolidated:]` 部分估算字符数；只有未压缩部分超过 `CHAR_THRESHOLD` 时才触发压缩。方法 SHALL 返回更新后的 `last_consolidated` 值（压缩发生时返回 `last_consolidated + 1`，否则返回传入的原值）。

#### Scenario: Only unconsolidated portion checked against threshold
- **WHEN** `history` 有 10 条消息，`last_consolidated=2`，`history[2:]` 总字符 < 40000
- **THEN** `maybe_consolidate` 返回 `2`（原值），不触发压缩，不修改 history

#### Scenario: Consolidation advances last_consolidated by 1
- **WHEN** 压缩成功，新 summary 插入 history[last_consolidated] 位置
- **THEN** 返回 `last_consolidated + 1`，已压缩的 summary 前缀不再参与下次估算

#### Scenario: Consolidated prefix preserved in history after compression
- **WHEN** `last_consolidated=1`（history[0] 是旧 summary），压缩 history[1:]中的旧消息
- **THEN** 压缩后 history 为：`[旧 summary, 新 summary, 保留的近期消息]`，`last_consolidated=2`

#### Scenario: Failed LLM call returns unchanged last_consolidated
- **WHEN** `_summarize` 抛出异常
- **THEN** history 保持不变，返回传入的 `last_consolidated` 原值
