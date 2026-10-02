"""recommendation_boundary 领域资料的基础结构。

本模块只定义推荐兴趣边界自主管理领域的事件种类、交换字段与领域约束，
供业务、运营和研发在同一套术语下讨论后续服务；不包含真实个人信息，
也不承担推荐模型训练——模型侧只通过这里定义的稳定契约与本服务交互。
"""

from __future__ import annotations

# --- 事件种类 -------------------------------------------------------------

EVENT_KINDS = (
    "SIGNAL_OBSERVED",           # 原始信号：观看、收藏、主动搜索、负反馈、运营活动
    "INTEREST_INFERRED",         # 兴趣条目写入或更新（人类化可读、带来源与有效期）
    "BOUNDARY_CHANGED",          # 用户调整条目、重置或限制推断、配置探索边界
    "PROFILE_ACCESSED",          # 推荐引擎取用画像，登记策略版本与用途
    "RECOMMENDATION_EXPLAINED",  # 客服视角：解释一次推荐用了哪些仍有效的信号
    "WITHDRAWAL_PROPAGATED",     # 撤回请求向所有活跃设备与缓存传播
    "WITHDRAWAL_VERIFIED",       # 验证撤回在设备与缓存过期后不再参与新决策
)

REQUIRED_FIELDS = ("event_id", "kind", "occurred_at", "subject_id", "payload")

# --- 枚举 -----------------------------------------------------------------

# 五类信号分别处理，不得混为一谈
SIGNAL_TYPES = ("watch", "favorite", "search", "negative_feedback", "campaign")

# 负反馈必须显式标注作用范围：单条作品、主题还是整个账号
NEGATIVE_FEEDBACK_SCOPES = ("item", "topic", "account")

SENSITIVITY_LEVELS = ("normal", "sensitive")

# 推断依据；其中 accidental_dwell（偶然停留）不足以支撑敏感主题的长期画像
INFERENCE_BASIS = (
    "repeated_watch",
    "favorite",
    "explicit_search",
    "campaign_assignment",
    "accidental_dwell",
)

BOUNDARY_ACTIONS = (
    "adjust_entry",
    "reset_category",
    "restrict_inference",
    "configure_exploration",
)

ACCESS_PURPOSES = ("organic_feed", "exploration", "ads")
ACCESS_CHANNELS = ("organic", "ads")

# 多样性探索的内容安全边界档位
SAFETY_BOUNDARIES = ("strict", "standard")

WITHDRAWAL_STATES = ("pending", "propagating", "effective")

# 重置或限制某类推断时，必须同时注销别名组，旧策略不得通过别名再次恢复
_ALIAS_GUARD_ACTIONS = ("reset_category", "restrict_inference")


# --- 校验入口 -------------------------------------------------------------

def validate_event(record: dict) -> list[str]:
    """检查事件是否具备可交换的最小字段并满足领域约束。

    返回问题字段名列表（嵌套字段用点号表示），空列表表示通过。
    """
    problems = [name for name in REQUIRED_FIELDS if name not in record]
    kind = record.get("kind")
    if kind not in EVENT_KINDS:
        problems.append("kind")
        return problems
    payload = record.get("payload")
    if not isinstance(payload, dict):
        if "payload" not in problems:
            problems.append("payload")
        return problems
    problems += _KIND_VALIDATORS[kind](payload)
    return problems


# --- 各类事件的载荷约束 ---------------------------------------------------

def _validate_signal_observed(payload: dict) -> list[str]:
    problems = _missing(payload, ("signal_type", "target_id", "sensitivity"))
    problems += _enum_problem(payload, "signal_type", SIGNAL_TYPES)
    problems += _enum_problem(payload, "sensitivity", SENSITIVITY_LEVELS)
    # 负反馈必须说清作用于单条作品、主题还是整个账号
    if payload.get("signal_type") == "negative_feedback":
        problems += _missing(payload, ("feedback_scope",))
        problems += _enum_problem(payload, "feedback_scope", NEGATIVE_FEEDBACK_SCOPES)
    return problems


def _validate_interest_inferred(payload: dict) -> list[str]:
    problems = _missing(payload, (
        "entry_id", "human_label", "source_signal_ids",
        "basis", "sensitivity", "expires_at",
    ))
    problems += _enum_problem(payload, "basis", INFERENCE_BASIS)
    problems += _enum_problem(payload, "sensitivity", SENSITIVITY_LEVELS)
    if "source_signal_ids" in payload and not _is_non_empty_list(payload["source_signal_ids"]):
        problems.append("payload.source_signal_ids")
    # 敏感主题不得仅凭偶然停留写入长期画像
    if payload.get("sensitivity") == "sensitive" and payload.get("basis") == "accidental_dwell":
        problems.append("payload.basis")
    return problems


def _validate_boundary_changed(payload: dict) -> list[str]:
    problems = _missing(payload, ("action", "scope"))
    problems += _enum_problem(payload, "action", BOUNDARY_ACTIONS)
    action = payload.get("action")
    if action in _ALIAS_GUARD_ACTIONS:
        problems += _missing(payload, ("revoked_alias_group",))
    if action == "configure_exploration":
        if "exploration" not in payload:
            problems.append("payload.exploration")
        else:
            problems += _validate_exploration(payload["exploration"])
    return problems


def _validate_profile_accessed(payload: dict) -> list[str]:
    # 每次取用画像都必须登记策略版本与用途
    problems = _missing(payload, ("accessor", "policy_version", "purpose", "channel"))
    problems += _enum_problem(payload, "purpose", ACCESS_PURPOSES)
    problems += _enum_problem(payload, "channel", ACCESS_CHANNELS)
    purpose, channel = payload.get("purpose"), payload.get("channel")
    # 广告与自然推荐明确分流：ads 用途只能走 ads 通道，反之亦然
    if purpose == "ads" and channel is not None and channel != "ads":
        problems.append("payload.channel")
    if channel == "ads" and purpose is not None and purpose != "ads":
        problems.append("payload.purpose")
    # 多样性探索必须携带用户可配置的频率与内容安全边界
    if purpose == "exploration":
        if "exploration" not in payload:
            problems.append("payload.exploration")
        else:
            problems += _validate_exploration(payload["exploration"])
    return problems


def _validate_recommendation_explained(payload: dict) -> list[str]:
    problems = _missing(payload, (
        "recommendation_id", "policy_version", "purpose", "channel", "signals_used",
    ))
    problems += _enum_problem(payload, "purpose", ACCESS_PURPOSES)
    problems += _enum_problem(payload, "channel", ACCESS_CHANNELS)
    signals = payload.get("signals_used")
    if signals is not None:
        if not _is_non_empty_list(signals):
            problems.append("payload.signals_used")
        else:
            for index, item in enumerate(signals):
                if not isinstance(item, dict):
                    problems.append(f"payload.signals_used[{index}]")
                    continue
                problems += [
                    f"payload.signals_used[{index}].{name}"
                    for name in ("entry_id", "still_valid", "expires_at")
                    if name not in item
                ]
                if "still_valid" in item and not isinstance(item["still_valid"], bool):
                    problems.append(f"payload.signals_used[{index}].still_valid")
    return problems


def _validate_withdrawal_propagated(payload: dict) -> list[str]:
    problems = _missing(payload, (
        "withdrawal_id", "scope", "revoked_alias_group",
        "device_ids", "cache_expires_at", "state",
    ))
    problems += _enum_problem(payload, "state", WITHDRAWAL_STATES)
    if "device_ids" in payload and not _is_non_empty_list(payload["device_ids"]):
        problems.append("payload.device_ids")
    return problems


def _validate_withdrawal_verified(payload: dict) -> list[str]:
    problems = _missing(payload, (
        "withdrawal_id", "verified_at", "devices_confirmed",
        "caches_expired", "participates_in_new_decisions",
    ))
    if "devices_confirmed" in payload and not isinstance(payload["devices_confirmed"], list):
        problems.append("payload.devices_confirmed")
    # 撤回只有在缓存过期后才算生效
    if "caches_expired" in payload and payload["caches_expired"] is not True:
        problems.append("payload.caches_expired")
    # 验证记录必须确认撤回信号不再参与新决策
    if ("participates_in_new_decisions" in payload
            and payload["participates_in_new_decisions"] is not False):
        problems.append("payload.participates_in_new_decisions")
    return problems


# --- 内部工具 -------------------------------------------------------------

def _validate_exploration(config, prefix: str = "payload.exploration") -> list[str]:
    if not isinstance(config, dict):
        return [prefix]
    problems = [
        f"{prefix}.{name}"
        for name in ("max_frequency_per_day", "safety_boundary")
        if name not in config
    ]
    frequency = config.get("max_frequency_per_day")
    if frequency is not None and (
        isinstance(frequency, bool) or not isinstance(frequency, int) or frequency <= 0
    ):
        problems.append(f"{prefix}.max_frequency_per_day")
    boundary = config.get("safety_boundary")
    if boundary is not None and boundary not in SAFETY_BOUNDARIES:
        problems.append(f"{prefix}.safety_boundary")
    return problems


def _missing(payload: dict, fields) -> list[str]:
    return [f"payload.{name}" for name in fields if name not in payload]


def _enum_problem(payload: dict, field: str, allowed) -> list[str]:
    if field not in payload:
        return []  # 缺失由 _missing 报告
    return [] if payload[field] in allowed else [f"payload.{field}"]


def _is_non_empty_list(value) -> bool:
    return isinstance(value, list) and len(value) > 0


_KIND_VALIDATORS = {
    "SIGNAL_OBSERVED": _validate_signal_observed,
    "INTEREST_INFERRED": _validate_interest_inferred,
    "BOUNDARY_CHANGED": _validate_boundary_changed,
    "PROFILE_ACCESSED": _validate_profile_accessed,
    "RECOMMENDATION_EXPLAINED": _validate_recommendation_explained,
    "WITHDRAWAL_PROPAGATED": _validate_withdrawal_propagated,
    "WITHDRAWAL_VERIFIED": _validate_withdrawal_verified,
}
