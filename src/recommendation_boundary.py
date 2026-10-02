"""推荐兴趣边界服务的领域事件约定、最小校验与解释辅助。

本模块只描述领域契约，不连接生产环境、不训练模型：

- 事件名称与负载字段是推荐引擎、客服工具与边界服务之间的稳定接口；
- ``validate_event`` 在写入事件时拦截违反权益约定的记录；
- ``evaluate_withdrawal`` 用于验证撤回是否已覆盖全部活跃设备与缓存；
- ``explain_decision`` 让客服解释一次推荐实际使用了哪些画像信号，
  以及这些信号在查询时刻是否仍然有效。
"""

from __future__ import annotations

from datetime import datetime

# ---------------------------------------------------------------------------
# 事件种类
# ---------------------------------------------------------------------------

SIGNAL_OBSERVED = "SIGNAL_OBSERVED"
INTEREST_INFERRED = "INTEREST_INFERRED"
BOUNDARY_CHANGED = "BOUNDARY_CHANGED"
PROFILE_ACCESSED = "PROFILE_ACCESSED"
WITHDRAWAL_PROPAGATED = "WITHDRAWAL_PROPAGATED"

EVENT_KINDS = [
    SIGNAL_OBSERVED,
    INTEREST_INFERRED,
    BOUNDARY_CHANGED,
    PROFILE_ACCESSED,
    WITHDRAWAL_PROPAGATED,
]

REQUIRED_FIELDS = ("event_id", "kind", "occurred_at", "subject_id", "payload")

# ---------------------------------------------------------------------------
# 词表：信号来源、负反馈粒度、敏感度、留存级别
# ---------------------------------------------------------------------------

WATCH = "WATCH"                    # 观看（含偶然停留）
FAVORITE = "FAVORITE"              # 收藏 / 点赞等主动表态
SEARCH = "SEARCH"                  # 主动搜索
NEGATIVE_FEEDBACK = "NEGATIVE_FEEDBACK"  # “不感兴趣”等负反馈
CAMPAIGN = "CAMPAIGN"              # 运营活动（商业性来源）

SIGNAL_SOURCES = (WATCH, FAVORITE, SEARCH, NEGATIVE_FEEDBACK, CAMPAIGN)

# 负反馈必须显式声明作用粒度，解决“到底作用于作品、主题还是账号”的歧义
FEEDBACK_SCOPE_ITEM = "ITEM"
FEEDBACK_SCOPE_TOPIC = "TOPIC"
FEEDBACK_SCOPE_CREATOR = "CREATOR"
NEGATIVE_FEEDBACK_SCOPES = (
    FEEDBACK_SCOPE_ITEM,
    FEEDBACK_SCOPE_TOPIC,
    FEEDBACK_SCOPE_CREATOR,
)

SENSITIVITY_STANDARD = "STANDARD"
SENSITIVITY_SENSITIVE = "SENSITIVE"
SENSITIVITY_LEVELS = (SENSITIVITY_STANDARD, SENSITIVITY_SENSITIVE)

RETENTION_SESSION = "SESSION"      # 会话内短期画像
RETENTION_LONG_TERM = "LONG_TERM"  # 长期画像
RETENTION_CLASSES = (RETENTION_SESSION, RETENTION_LONG_TERM)

# ---------------------------------------------------------------------------
# 词表：边界动作
# ---------------------------------------------------------------------------

RESET = "RESET"                       # 重置（切断重置前旧信号对推断的支撑）
SUPPRESS = "SUPPRESS"                 # 屏蔽某主题及其别名
LIFT_SUPPRESSION = "LIFT_SUPPRESSION" # 用户解除屏蔽
LIMIT_INFERENCE = "LIMIT_INFERENCE"   # 限制某类信号参与推断
SET_EXPLORATION_FREQUENCY = "SET_EXPLORATION_FREQUENCY"
SET_SAFETY_BOUNDARY = "SET_SAFETY_BOUNDARY"

BOUNDARY_ACTIONS = (
    RESET,
    SUPPRESS,
    LIFT_SUPPRESSION,
    LIMIT_INFERENCE,
    SET_EXPLORATION_FREQUENCY,
    SET_SAFETY_BOUNDARY,
)

SCOPE_ACCOUNT = "ACCOUNT"
SCOPE_CATEGORY = "CATEGORY"
SCOPE_TOPIC = "TOPIC"
SCOPE_SIGNAL_KIND = "SIGNAL_KIND"
SCOPE_SIGNAL = "SIGNAL"
SCOPE_INTEREST = "INTEREST"

# ---------------------------------------------------------------------------
# 词表：画像取用（推荐引擎每次读取都要登记）
# ---------------------------------------------------------------------------

CHANNEL_ORGANIC = "ORGANIC"  # 自然推荐 / 兴趣拓展
CHANNEL_ADS = "ADS"          # 广告投放
CHANNELS = (CHANNEL_ORGANIC, CHANNEL_ADS)

PURPOSE_RANK_ORGANIC = "RANK_ORGANIC"
PURPOSE_RANK_ADS = "RANK_ADS"
PURPOSE_EXPLORATION = "EXPLORATION"   # 多样性探索
PURPOSE_EXPLANATION = "EXPLANATION"   # 客服解释
PURPOSE_SAFETY_REVIEW = "SAFETY_REVIEW"
ACCESS_PURPOSES = (
    PURPOSE_RANK_ORGANIC,
    PURPOSE_RANK_ADS,
    PURPOSE_EXPLORATION,
    PURPOSE_EXPLANATION,
    PURPOSE_SAFETY_REVIEW,
)

# 广告与自然推荐明确分流：用途与允许的渠道必须一致
PURPOSE_ALLOWED_CHANNELS = {
    PURPOSE_RANK_ORGANIC: {CHANNEL_ORGANIC},
    PURPOSE_RANK_ADS: {CHANNEL_ADS},
    PURPOSE_EXPLORATION: {CHANNEL_ORGANIC},
    PURPOSE_EXPLANATION: {CHANNEL_ORGANIC, CHANNEL_ADS},
    PURPOSE_SAFETY_REVIEW: {CHANNEL_ORGANIC, CHANNEL_ADS},
}

# ---------------------------------------------------------------------------
# 词表：撤回传播
# ---------------------------------------------------------------------------

WITHDRAWAL_PENDING = "PENDING"
WITHDRAWAL_PROPAGATED_STATUS = "PROPAGATED"
WITHDRAWAL_STATUSES = (WITHDRAWAL_PENDING, WITHDRAWAL_PROPAGATED_STATUS)

ACK_PENDING = "PENDING"
ACK_ACKED = "ACKED"
DEVICE_ACK_STATUSES = (ACK_PENDING, ACK_ACKED)

CACHE_PENDING = "PENDING"
CACHE_EVICTED = "EVICTED"    # 已主动失效
CACHE_EXPIRED = "EXPIRED"    # 已超过声明的过期时刻
CACHE_STATUSES = (CACHE_PENDING, CACHE_EVICTED, CACHE_EXPIRED)

# 信号 / 兴趣条目在某时刻的有效状态
VALID = "VALID"
EXPIRED = "EXPIRED"
WITHDRAWN = "WITHDRAWN"
RESET = "RESET"
SUPPRESSED = "SUPPRESSED"

# ---------------------------------------------------------------------------
# 每类事件的最小负载字段
# ---------------------------------------------------------------------------

PAYLOAD_REQUIRED_FIELDS = {
    SIGNAL_OBSERVED: (
        "signal_id", "source", "topic_id", "label", "expires_at",
    ),
    INTEREST_INFERRED: (
        "interest_id", "topic_id", "label", "category", "aliases",
        "source_signal_ids", "sensitivity", "retention", "commercial",
        "expires_at", "policy_version",
    ),
    BOUNDARY_CHANGED: (
        "change_id", "action", "target", "reason", "effective_at",
    ),
    PROFILE_ACCESSED: (
        "access_id", "consumer", "policy_version", "purpose", "channel",
        "decision_id", "used_signal_ids", "used_interest_ids",
    ),
    WITHDRAWAL_PROPAGATED: (
        "withdrawal_id", "requested_at", "scope", "targets",
        "devices", "caches", "status",
    ),
}

SOURCE_EXTRA_FIELDS = {
    WATCH: ("dwell_ms",),
    SEARCH: ("query",),
    FAVORITE: ("target_id",),
    NEGATIVE_FEEDBACK: ("feedback_scope", "target_id"),
    CAMPAIGN: ("campaign_id",),
}


# ---------------------------------------------------------------------------
# 时间工具
# ---------------------------------------------------------------------------

def _ts(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 历史回放：在给定时刻之前的边界状态、撤回状态
# ---------------------------------------------------------------------------

def _boundary_events(history, t: datetime):
    for event in sorted(history, key=lambda e: e["occurred_at"]):
        if event.get("kind") != BOUNDARY_CHANGED:
            continue
        payload = event.get("payload") or {}
        effective_at = _ts(payload.get("effective_at")) or _ts(event["occurred_at"])
        if effective_at is not None and effective_at <= t:
            yield event, payload, effective_at


def _suppression_keys(history, t: datetime) -> set[str]:
    """当前仍生效的屏蔽键（含别名，防止旧策略换名恢复）。"""
    suppressed: set[str] = set()
    for _, payload, _ in _boundary_events(history, t):
        action = payload.get("action")
        target = payload.get("target") or {}
        keys = {target.get("id"), *payload.get("aliases", [])}
        keys.discard(None)
        if action == SUPPRESS:
            suppressed |= keys
        elif action == LIFT_SUPPRESSION:
            suppressed -= keys
    return suppressed


def _limited_sources(history, t: datetime) -> set[str]:
    """当前被限制参与推断的信号来源。"""
    limited: set[str] = set()
    for _, payload, _ in _boundary_events(history, t):
        if payload.get("action") != LIMIT_INFERENCE:
            continue
        target = payload.get("target") or {}
        if target.get("type") != SCOPE_SIGNAL_KIND or target.get("id") not in SIGNAL_SOURCES:
            continue
        if payload.get("enabled", True):
            limited.add(target["id"])
        else:
            limited.discard(target["id"])
    return limited


def _resets(history, t: datetime):
    for _, payload, effective_at in _boundary_events(history, t):
        if payload.get("action") == RESET:
            yield effective_at, payload.get("target") or {}


def _reset_covers(target: dict, item: dict) -> bool:
    scope_type = target.get("type")
    scope_id = target.get("id")
    if scope_type == SCOPE_ACCOUNT:
        return True
    if scope_type == SCOPE_CATEGORY:
        return item.get("category") == scope_id
    if scope_type == SCOPE_TOPIC:
        return item.get("topic_id") == scope_id
    return False


def _withdrawn_targets(history, t: datetime, kind: str | None = None) -> dict[str, datetime]:
    """已在 t 时刻前完成传播的撤回目标 -> 最早完成时刻。

    ``kind`` 取 SCOPE_SIGNAL / SCOPE_INTEREST 时只计入对应范围的撤回，
    账号级撤回对两者都生效。
    """
    withdrawn: dict[str, datetime] = {}
    for event in sorted(history, key=lambda e: e["occurred_at"]):
        if event.get("kind") != WITHDRAWAL_PROPAGATED:
            continue
        payload = event.get("payload") or {}
        if payload.get("status") != WITHDRAWAL_PROPAGATED_STATUS:
            continue
        scope_type = (payload.get("scope") or {}).get("type")
        if kind is not None and scope_type not in (kind, SCOPE_ACCOUNT):
            continue
        propagated_at = _ts(event["occurred_at"])
        if propagated_at is None or propagated_at > t:
            continue
        for target_id in payload.get("targets", []):
            if target_id not in withdrawn or propagated_at < withdrawn[target_id]:
                withdrawn[target_id] = propagated_at
    return withdrawn


def _index(history):
    signals: dict[str, dict] = {}
    interests: dict[str, dict] = {}
    for event in history:
        payload = event.get("payload") or {}
        if event.get("kind") == SIGNAL_OBSERVED:
            signals[payload.get("signal_id")] = event
        elif event.get("kind") == INTEREST_INFERRED:
            interests[payload.get("interest_id")] = event
    return signals, interests


# ---------------------------------------------------------------------------
# 有效状态判定
# ---------------------------------------------------------------------------

def signal_status_at(signal_event: dict, history, at: datetime) -> str:
    payload = signal_event["payload"]
    observed_at = _ts(signal_event["occurred_at"])
    expires_at = _ts(payload.get("expires_at"))
    if expires_at is not None and expires_at <= at:
        return EXPIRED
    withdrawn_at = _withdrawn_targets(history, at, SCOPE_SIGNAL).get(payload["signal_id"])
    if withdrawn_at is not None and observed_at is not None and withdrawn_at > observed_at:
        return WITHDRAWN
    for reset_at, target in _resets(history, at):
        if observed_at is not None and observed_at < reset_at and _reset_covers(target, payload):
            return RESET
    return VALID


def interest_status_at(interest_event: dict, history, at: datetime) -> str:
    payload = interest_event["payload"]
    inferred_at = _ts(interest_event["occurred_at"])
    if _ts(payload.get("expires_at")) is not None and _ts(payload["expires_at"]) <= at:
        return EXPIRED
    withdrawn_at = _withdrawn_targets(history, at, SCOPE_INTEREST).get(payload["interest_id"])
    if withdrawn_at is not None:
        return WITHDRAWN
    keys = {payload.get("topic_id"), *payload.get("aliases", [])}
    keys.discard(None)
    if keys & _suppression_keys(history, at):
        return SUPPRESSED
    for reset_at, target in _resets(history, at):
        if inferred_at is not None and inferred_at < reset_at and _reset_covers(target, payload):
            return RESET
    # 撤回或重置会沿派生关系传导：任一来源信号失效，派生出的兴趣条目
    # 在新决策中同样不可用，必须以剩余 / 新生信号重新推断
    signals_by_id, _ = _index(history)
    derived = [signal_status_at(signals_by_id[sid], history, at)
               for sid in payload.get("source_signal_ids", [])
               if sid in signals_by_id]
    if WITHDRAWN in derived:
        return WITHDRAWN
    if RESET in derived:
        return RESET
    if derived and all(status == EXPIRED for status in derived):
        return EXPIRED
    return VALID


# ---------------------------------------------------------------------------
# 事件校验
# ---------------------------------------------------------------------------

def validate_event(record: dict, history=()) -> list[str]:
    """校验一条事件。返回问题代码列表，空列表表示符合领域契约。

    传入 ``history``（同一账号此前的事件，可乱序）时会额外校验跨事件不变量，
    例如敏感主题推断依据、重置/屏蔽后的别名复活、取用已撤回信号等。
    """
    problems = [name for name in REQUIRED_FIELDS if name not in record]
    kind = record.get("kind")
    if kind not in EVENT_KINDS:
        problems.append("kind")
        return problems

    occurred_at = _ts(record.get("occurred_at"))
    if occurred_at is None:
        problems.append("occurred_at")
        return problems

    payload = record.get("payload")
    if not isinstance(payload, dict):
        problems.append("payload")
        return problems

    for field in PAYLOAD_REQUIRED_FIELDS[kind]:
        if field not in payload:
            problems.append(f"payload.{field}")
    if problems:
        return problems

    # history 只包含调用方认定的既往事件（按时间顺序回放）；
    # 同一时刻的事件按到达顺序计入，避免边界变更因时间戳相同而漏生效
    prior = [e for e in history if _ts(e.get("occurred_at")) is not None
             and _ts(e["occurred_at"]) <= occurred_at]

    if kind == SIGNAL_OBSERVED:
        problems += _validate_signal(payload, occurred_at)
    elif kind == INTEREST_INFERRED:
        problems += _validate_interest(payload, occurred_at, prior)
    elif kind == BOUNDARY_CHANGED:
        problems += _validate_boundary(payload)
    elif kind == PROFILE_ACCESSED:
        problems += _validate_access(payload, occurred_at, prior)
    elif kind == WITHDRAWAL_PROPAGATED:
        problems += _validate_withdrawal(record, payload, occurred_at)
    return problems


def _validate_signal(payload: dict, at: datetime | None = None) -> list[str]:
    problems: list[str] = []
    source = payload.get("source")
    if source not in SIGNAL_SOURCES:
        problems.append("payload.source")
        return problems
    for field in SOURCE_EXTRA_FIELDS[source]:
        if field not in payload:
            problems.append(f"payload.{field}")
    if source == NEGATIVE_FEEDBACK and payload.get("feedback_scope") not in NEGATIVE_FEEDBACK_SCOPES:
        problems.append("payload.feedback_scope")
    if source == WATCH and not isinstance(payload.get("dwell_ms"), int):
        problems.append("payload.dwell_ms")
    expires_at = _ts(payload.get("expires_at"))
    if expires_at is None:
        problems.append("payload.expires_at")
    elif at is not None and expires_at <= at:
        problems.append("expires_before_observed")
    if not isinstance(payload.get("commercial", False), bool):
        problems.append("payload.commercial")
    return problems


def _is_corroborating(signal_payload: dict) -> bool:
    """可作为敏感主题长期画像依据的信号：明确行为，而非偶然停留。"""
    source = signal_payload.get("source")
    if source in (FAVORITE, SEARCH):
        return True
    # 完整观看 / 非偶然停留的主动观看可以作为依据；极短误触停留不行
    if source == WATCH and not signal_payload.get("incidental", False):
        return True
    return False


def _validate_interest(payload: dict, at: datetime, history: list[dict]) -> list[str]:
    problems: list[str] = []
    if payload.get("sensitivity") not in SENSITIVITY_LEVELS:
        problems.append("payload.sensitivity")
    if payload.get("retention") not in RETENTION_CLASSES:
        problems.append("payload.retention")
    if not isinstance(payload.get("commercial"), bool):
        problems.append("payload.commercial")
    if not isinstance(payload.get("aliases"), list):
        problems.append("payload.aliases")
    if not isinstance(payload.get("source_signal_ids"), list) or not payload["source_signal_ids"]:
        problems.append("payload.source_signal_ids")

    expires_at = _ts(payload.get("expires_at"))
    if expires_at is None:
        problems.append("payload.expires_at")
    elif expires_at <= at:
        problems.append("expires_before_inferred")

    signals_by_id, _ = _index(history)
    limited = _limited_sources(history, at)
    suppressed = _suppression_keys(history, at)

    aliases = payload.get("aliases") if isinstance(payload.get("aliases"), list) else []
    keys = {payload.get("topic_id"), *aliases}
    keys.discard(None)
    if keys & suppressed:
        problems.append("suppressed_alias_revival")

    cited: list[dict] = []
    for signal_id in payload.get("source_signal_ids", []) or []:
        signal_event = signals_by_id.get(signal_id)
        if signal_event is None:
            problems.append(f"unknown_source_signal:{signal_id}")
            continue
        cited.append(signal_event)
        signal_payload = signal_event["payload"]
        status = signal_status_at(signal_event, history, at)
        if status != VALID:
            problems.append(f"source_signal_not_valid:{signal_id}:{status}")
        if signal_payload.get("source") in limited:
            problems.append(f"source_signal_kind_limited:{signal_id}")
        # 重置后只能引用重置之后新产生的信号；旧信号不得借新推断复活。
        # 账号/品类级重置覆盖该兴趣时，其引用的所有旧信号一律失效；
        # 主题级重置只要求同主题（含别名）信号晚于重置。
        observed_at = _ts(signal_event["occurred_at"])
        same_topic = signal_payload.get("topic_id") == payload.get("topic_id") or \
            signal_payload.get("topic_id") in (payload.get("aliases") or [])
        if observed_at is not None:
            for reset_at, target in _resets(history, at):
                if observed_at >= reset_at or not _reset_covers(target, payload):
                    continue
                if target.get("type") == SCOPE_TOPIC and not same_topic:
                    continue
                problems.append(f"pre_reset_signal:{signal_id}")

    if payload.get("sensitivity") == SENSITIVITY_SENSITIVE \
            and payload.get("retention") == RETENTION_LONG_TERM \
            and not any(_is_corroborating(e["payload"]) for e in cited):
        problems.append("sensitive_long_term_without_corroboration")

    # 商业与自然分流：兴趣条目的商业性必须与其来源信号一致，
    # 运营活动信号不得写入自然画像，自然信号也不得包装成投放兴趣
    derived_commercial = any(e["payload"].get("commercial") for e in cited)
    if not problems and payload.get("commercial") != derived_commercial:
        problems.append("commercial_origin_mismatch")

    return problems


def _validate_boundary(payload: dict) -> list[str]:
    problems: list[str] = []
    action = payload.get("action")
    target = payload.get("target")
    if action not in BOUNDARY_ACTIONS:
        problems.append("payload.action")
        return problems
    if not isinstance(target, dict) or target.get("type") not in (
        SCOPE_ACCOUNT, SCOPE_CATEGORY, SCOPE_TOPIC, SCOPE_SIGNAL_KIND,
    ):
        problems.append("payload.target")
        return problems

    if action in (RESET,) and target["type"] not in (SCOPE_ACCOUNT, SCOPE_CATEGORY, SCOPE_TOPIC):
        problems.append("payload.target")
    if action in (SUPPRESS, LIFT_SUPPRESSION) and target["type"] != SCOPE_TOPIC:
        problems.append("payload.target")
    if action == LIMIT_INFERENCE:
        if target["type"] != SCOPE_SIGNAL_KIND or target.get("id") not in SIGNAL_SOURCES:
            problems.append("payload.target")
        if not isinstance(payload.get("enabled"), bool):
            problems.append("payload.enabled")
    if action == SET_EXPLORATION_FREQUENCY:
        frequency = (payload.get("constraints") or {}).get("max_frequency_per_100")
        if not isinstance(frequency, int) or isinstance(frequency, bool) \
                or not 0 <= frequency <= 100:
            problems.append("payload.constraints.max_frequency_per_100")
    if action == SET_SAFETY_BOUNDARY and not payload.get("safety_boundary_version"):
        problems.append("payload.safety_boundary_version")
    if action == SUPPRESS and not isinstance(payload.get("aliases", []), list):
        problems.append("payload.aliases")
    return problems


def _latest_settings(history: list[dict], at: datetime):
    frequency = None
    safety_version = None
    for _, boundary_payload, _ in _boundary_events(history, at):
        if boundary_payload.get("action") == SET_EXPLORATION_FREQUENCY:
            frequency = (boundary_payload.get("constraints") or {}).get("max_frequency_per_100")
        if boundary_payload.get("action") == SET_SAFETY_BOUNDARY:
            safety_version = boundary_payload.get("safety_boundary_version")
    return frequency, safety_version


def _validate_access(payload: dict, at: datetime, history: list[dict]) -> list[str]:
    problems: list[str] = []
    purpose = payload.get("purpose")
    channel = payload.get("channel")
    if purpose not in ACCESS_PURPOSES:
        problems.append("payload.purpose")
    if channel not in CHANNELS:
        problems.append("payload.channel")
    if purpose in PURPOSE_ALLOWED_CHANNELS and channel in CHANNELS \
            and channel not in PURPOSE_ALLOWED_CHANNELS[purpose]:
        problems.append("purpose_channel_mismatch")

    constraints = payload.get("constraints")
    if purpose == PURPOSE_EXPLORATION:
        if not isinstance(constraints, dict) \
                or not isinstance(constraints.get("max_frequency_per_100"), int) \
                or not constraints.get("safety_boundary_version"):
            problems.append("exploration_constraints_required")
        else:
            configured_frequency, configured_safety = _latest_settings(history, at)
            if configured_frequency is not None \
                    and constraints["max_frequency_per_100"] != configured_frequency:
                problems.append("exploration_frequency_mismatch")
            if configured_safety is not None \
                    and constraints["safety_boundary_version"] != configured_safety:
                problems.append("exploration_safety_mismatch")

    signals_by_id, interests_by_id = _index(history)
    for signal_id in payload.get("used_signal_ids", []):
        signal_event = signals_by_id.get(signal_id)
        if signal_event is None:
            problems.append(f"unknown_used_signal:{signal_id}")
            continue
        status = signal_status_at(signal_event, history, at)
        if status != VALID:
            problems.append(f"used_signal_not_valid:{signal_id}:{status}")
        # 自然推荐渠道不得消费商业性（运营活动）信号
        if channel == CHANNEL_ORGANIC and signal_event["payload"].get("commercial"):
            problems.append(f"commercial_signal_in_organic:{signal_id}")

    for interest_id in payload.get("used_interest_ids", []):
        interest_event = interests_by_id.get(interest_id)
        if interest_event is None:
            problems.append(f"unknown_used_interest:{interest_id}")
            continue
        status = interest_status_at(interest_event, history, at)
        if status != VALID:
            problems.append(f"used_interest_not_valid:{interest_id}:{status}")
        if channel == CHANNEL_ORGANIC and interest_event["payload"].get("commercial"):
            problems.append(f"commercial_interest_in_organic:{interest_id}")

    return problems


def _validate_withdrawal(record: dict, payload: dict, at: datetime) -> list[str]:
    problems: list[str] = []
    scope = payload.get("scope")
    if not isinstance(scope, dict) or scope.get("type") not in (
        SCOPE_SIGNAL, SCOPE_INTEREST, SCOPE_ACCOUNT,
    ):
        problems.append("payload.scope")
    if not isinstance(payload.get("targets"), list) or not payload["targets"]:
        problems.append("payload.targets")
    if payload.get("status") not in WITHDRAWAL_STATUSES:
        problems.append("payload.status")

    devices = payload.get("devices")
    caches = payload.get("caches")
    if not isinstance(devices, list):
        problems.append("payload.devices")
        devices = []
    if not isinstance(caches, list):
        problems.append("payload.caches")
        caches = []

    active_devices = set()
    for device in devices:
        if not isinstance(device, dict) or device.get("status") not in DEVICE_ACK_STATUSES:
            problems.append("payload.devices.status")
            continue
        active_devices.add(device.get("device_id"))
        if device["status"] == ACK_ACKED:
            acked_at = _ts(device.get("acked_at"))
            if acked_at is None or acked_at > at:
                problems.append(f"device_ack_time:{device.get('device_id')}")

    for cache in caches:
        if not isinstance(cache, dict) or cache.get("status") not in CACHE_STATUSES:
            problems.append("payload.caches.status")
            continue
        if cache["status"] == CACHE_EVICTED:
            evicted_at = _ts(cache.get("evicted_at"))
            if evicted_at is None or evicted_at > at:
                problems.append(f"cache_evict_time:{cache.get('cache_scope')}")
        elif cache["status"] == CACHE_EXPIRED:
            expires_at = _ts(cache.get("expires_at"))
            if expires_at is None or expires_at > at:
                problems.append(f"cache_expire_time:{cache.get('cache_scope')}")

    # 自洽检查：声明 PROPAGATED 时，事件中枚举的设备与缓存必须确实全部完成
    if payload.get("status") == WITHDRAWAL_PROPAGATED_STATUS and not problems:
        state, _ = evaluate_withdrawal(record, active_devices, at)
        if state != WITHDRAWAL_PROPAGATED_STATUS:
            problems.append("withdrawal_not_fully_propagated")
    return problems


# ---------------------------------------------------------------------------
# 撤回传播验证（供边界服务在收到设备/缓存回执后调用）
# ---------------------------------------------------------------------------

def evaluate_withdrawal(record: dict, active_device_ids=(), at=None) -> tuple[str, list[str]]:
    """判断撤回请求在 ``at`` 时刻是否覆盖全部活跃设备与缓存。

    返回 ``(状态, 未完成原因)``。``at`` 默认为事件发生时刻，可传 ISO 字符串
    或 ``datetime``。活跃设备清单以服务端会话登记为准，事件中的 devices 仅是回执。
    """
    payload = record.get("payload") or {}
    if isinstance(at, str):
        at = _ts(at)
    if at is None:
        at = _ts(record.get("occurred_at"))

    reasons: list[str] = []
    acked: dict[str, datetime] = {}
    for device in payload.get("devices", []):
        acked_at = _ts(device.get("acked_at"))
        if device.get("status") == ACK_ACKED and acked_at is not None and acked_at <= at:
            acked[device.get("device_id")] = acked_at
    for device_id in active_device_ids:
        if device_id not in acked:
            reasons.append(f"device_pending:{device_id}")

    for cache in payload.get("caches", []):
        scope = cache.get("cache_scope")
        if cache.get("status") == CACHE_EVICTED:
            evicted_at = _ts(cache.get("evicted_at"))
            if evicted_at is not None and evicted_at <= at:
                continue
        expires_at = _ts(cache.get("expires_at"))
        if expires_at is not None and expires_at <= at:
            continue
        reasons.append(f"cache_pending:{scope}")

    return (WITHDRAWAL_PROPAGATED_STATUS if not reasons else WITHDRAWAL_PENDING), reasons


# ---------------------------------------------------------------------------
# 账号自查：当前仍然有效的人类化兴趣条目、来源与有效期
# ---------------------------------------------------------------------------

def readable_profile(history, at=None) -> dict:
    """生成账号在 ``at`` 时刻可读的兴趣画像视图。

    只返回当时仍有效的兴趣条目；每条给出可读名称、来源信号（分别标注
    观看 / 收藏 / 搜索 / 负反馈 / 运营活动）、有效期、敏感度与留存级别，
    并按自然 / 投放分流，供账号自查与调整。
    """
    if isinstance(at, str):
        at = _ts(at)
    if at is None:
        at = max(_ts(e["occurred_at"]) for e in history
                 if _ts(e.get("occurred_at")) is not None)

    signals_by_id, interests_by_id = _index(history)
    organic, ads = [], []
    for interest_event in interests_by_id.values():
        payload = interest_event["payload"]
        if interest_status_at(interest_event, history, at) != VALID:
            continue
        sources = []
        for signal_id in payload.get("source_signal_ids", []):
            signal_event = signals_by_id.get(signal_id)
            if signal_event is None:
                continue
            signal_payload = signal_event["payload"]
            if signal_status_at(signal_event, history, at) != VALID:
                continue
            sources.append({
                "signal_id": signal_id,
                "label": signal_payload.get("label"),
                "source": signal_payload.get("source"),
                "observed_at": signal_event.get("occurred_at"),
                "expires_at": signal_payload.get("expires_at"),
            })
        row = {
            "interest_id": payload["interest_id"],
            "label": payload.get("label"),
            "topic_id": payload.get("topic_id"),
            "category": payload.get("category"),
            "aliases": payload.get("aliases"),
            "sensitivity": payload.get("sensitivity"),
            "retention": payload.get("retention"),
            "expires_at": payload.get("expires_at"),
            "policy_version": payload.get("policy_version"),
            "sources": sources,
        }
        (ads if payload.get("commercial") else organic).append(row)
    return {"as_of": at.isoformat(), "organic_interests": organic, "ad_interests": ads}


# ---------------------------------------------------------------------------
# 客服解释：一次推荐用了哪些信号，现在是否仍有效
# ---------------------------------------------------------------------------

def explain_decision(history, decision_id: str, at=None) -> dict:
    """根据事件历史还原一次画像取用，供客服做可读解释。

    ``at`` 为查询时刻（默认历史中最晚事件时刻）。每个被使用的信号/兴趣条目
    同时给出决策时刻与查询时刻的有效状态，便于回答“现在撤回是否已经生效”。
    """
    access_event = next(
        (e for e in history
         if e.get("kind") == PROFILE_ACCESSED
         and (e.get("payload") or {}).get("decision_id") == decision_id),
        None,
    )
    if access_event is None:
        raise ValueError(f"unknown decision: {decision_id}")

    access = access_event["payload"]
    decision_at = _ts(access_event["occurred_at"])
    if isinstance(at, str):
        at = _ts(at)
    if at is None:
        at = max(_ts(e["occurred_at"]) for e in history
                 if _ts(e.get("occurred_at")) is not None)

    signals_by_id, interests_by_id = _index(history)

    def describe_signal(signal_id):
        event = signals_by_id.get(signal_id)
        if event is None:
            return {"signal_id": signal_id, "status_at_query": "UNKNOWN"}
        p = event["payload"]
        return {
            "signal_id": signal_id,
            "label": p.get("label"),
            "source": p.get("source"),
            "commercial": bool(p.get("commercial")),
            "topic_id": p.get("topic_id"),
            "expires_at": p.get("expires_at"),
            "status_at_decision": signal_status_at(event, history, decision_at),
            "status_at_query": signal_status_at(event, history, at),
        }

    def describe_interest(interest_id):
        event = interests_by_id.get(interest_id)
        if event is None:
            return {"interest_id": interest_id, "status_at_query": "UNKNOWN"}
        p = event["payload"]
        return {
            "interest_id": interest_id,
            "label": p.get("label"),
            "topic_id": p.get("topic_id"),
            "aliases": p.get("aliases"),
            "sensitivity": p.get("sensitivity"),
            "commercial": bool(p.get("commercial")),
            "expires_at": p.get("expires_at"),
            "status_at_decision": interest_status_at(event, history, decision_at),
            "status_at_query": interest_status_at(event, history, at),
        }

    return {
        "decision_id": decision_id,
        "occurred_at": access_event["occurred_at"],
        "consumer": access.get("consumer"),
        "policy_version": access.get("policy_version"),
        "purpose": access.get("purpose"),
        "channel": access.get("channel"),
        "exploration_constraints": access.get("constraints"),
        "signals": [describe_signal(sid) for sid in access.get("used_signal_ids", [])],
        "interests": [describe_interest(iid) for iid in access.get("used_interest_ids", [])],
    }
