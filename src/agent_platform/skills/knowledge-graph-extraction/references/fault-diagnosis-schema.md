# Domain Pattern: Fault-Diagnosis / FMEA Knowledge Graphs

When the source document is an equipment maintenance manual, troubleshooting
guide, or FMEA (Failure Mode and Effects Analysis) report, use this schema
pattern. It captures the causal chain from component to failure to root cause,
with diagnostic indicators and downstream effects.

## Entity Types

| Type | Description | Example (Chinese) |
|------|-------------|-------------------|
| 系统 | Top-level system | 离心泵循环系统 |
| 部件 | Physical component or subsystem | 电动机, 机械密封, 叶轮, 变频器 |
| 故障模式 | Observable failure state | 电动机过热, 机械密封泄漏 |
| 故障原因 | Root cause of a failure | 绕组绝缘老化, 动环O形圈老化硬化 |
| 判定指标 | Quantified diagnostic threshold | 振动值超过4.5mm/s, 温度超过75℃ |
| 影响 | Downstream effect of a failure | 热继电器动作停机 |
| 处理措施 | Repair or mitigation action | 更换密封, 清洗滤网 |

## Relationship Types

| Type | Direction | Meaning | Example |
|------|-----------|---------|---------|
| 包含 | SYS/部件 → 部件 | Part-of hierarchy | 电动机 → 包含 → 冷却风扇 |
| 故障表现 | 部件 → 故障模式 | Component exhibits failure | 机械密封 → 故障表现 → 机械密封泄漏 |
| 可能原因 | 故障模式 → 故障原因 | Failure is caused by | 机械密封泄漏 → 可能原因 → 动环O形圈老化硬化 |
| 判定阈值 | 故障模式 → 判定指标 | Diagnostic criterion | 轴承温度过高 → 判定阈值 → 温度超过75℃ |
| 导致 | 故障模式/原因 → 影响 | Failure causes effect | 电动机过热 → 导致 → 热继电器动作停机 |

## Design Notes

- **Component granularity.** Go 1–2 levels deep. "电动机 → 包含 → 冷却风扇"
  is useful; "冷却风扇 → 包含 → 风扇叶片" is usually too fine. Stop when the
  part stops participating in any documented failure mode.
- **Cause chaining.** A cause can itself be a failure mode of a sub-component.
  E.g. "叶轮不平衡" is both a cause (of 泵体振动超标) and a failure mode
  (of 叶轮). Model it as one `故障原因` entity; the assembler handles bridges.
- **Indicator entities.** Name them as the threshold statement, not the parameter
  name. Use "振动值超过4.5mm/s" not "振动幅值" — the former is the diagnostic
  fact, the latter is just a variable name.
- **Effect chaining.** If an effect triggers another failure mode (e.g. "热继
  电器动作停机" causes "电动机无法启动"), model each link separately.

## schema.json Template

```json
{
  "domain": "equipment-fault-diagnosis",
  "entity_types": [
    { "type": "系统", "description": "设备系统整体" },
    { "type": "部件", "description": "组成部件或子组件" },
    { "type": "故障模式", "description": "部件发生的具体故障表现" },
    { "type": "故障原因", "description": "导致故障的根本原因" },
    { "type": "判定指标", "description": "量化判定阈值" },
    { "type": "影响", "description": "故障导致的后果" },
    { "type": "处理措施", "description": "解决或预防故障的操作" }
  ],
  "relationship_types": [
    { "type": "包含", "source_types": ["系统","部件"], "target_types": ["部件"], "symmetric": false,
      "description": "系统或部件包含子部件" },
    { "type": "故障表现", "source_types": ["部件"], "target_types": ["故障模式"], "symmetric": false,
      "description": "部件发生的故障模式" },
    { "type": "可能原因", "source_types": ["故障模式"], "target_types": ["故障原因"], "symmetric": false,
      "description": "故障模式的可能原因" },
    { "type": "判定阈值", "source_types": ["故障模式"], "target_types": ["判定指标"], "symmetric": false,
      "description": "故障模式的判定条件" },
    { "type": "导致", "source_types": ["故障模式","故障原因"], "target_types": ["影响"], "symmetric": false,
      "description": "故障或原因导致的后果" }
  ]
}
```
