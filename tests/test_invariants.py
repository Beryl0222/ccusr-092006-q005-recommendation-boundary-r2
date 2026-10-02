"""推荐兴趣边界服务的领域不变量测试。

所有数据均为虚构，时间固定在 2026-09。测试以“先发生的事件作为 history”
逐条回放，校验跨事件不变量。
"""

from __future__ import annotations

import unittest

from src.recommendation_boundary import (
    ACK_ACKED,
    CAMPAIGN,
    CACHE_EVICTED,
    CACHE_EXPIRED,
    CACHE_PENDING,
    CHANNEL_ADS,
    CHANNEL_ORGANIC,
    EVENT_KINDS,
    EXPIRED,
    FAVORITE,
    FEEDBACK_SCOPE_CREATOR,
    FEEDBACK_SCOPE_ITEM,
    FEEDBACK_SCOPE_TOPIC,
    LIMIT_INFERENCE,
    LIFT_SUPPRESSION,
    NEGATIVE_FEEDBACK,
    PURPOSE_EXPLORATION,
    PURPOSE_RANK_ADS,
    PURPOSE_RANK_ORGANIC,
    RESET,
    RETENTION_LONG_TERM,
    RETENTION_SESSION,
    SCOPE_ACCOUNT,
    SCOPE_CATEGORY,
    SCOPE_INTEREST,
    SCOPE_SIGNAL,
    SCOPE_SIGNAL_KIND,
    SCOPE_TOPIC,
    SEARCH,
    SENSITIVITY_SENSITIVE,
    SENSITIVITY_STANDARD,
    SIGNAL_OBSERVED,
    SUPPRESSED,
    SUPPRESS,
    VALID,
    WATCH,
    WITHDRAWAL_PENDING,
    WITHDRAWAL_PROPAGATED_STATUS,
    WITHDRAWN,
    evaluate_withdrawal,
    explain_decision,
    readable_profile,
    validate_event,
)

T0 = "2026-09-20T09:00:00+08:00"
T1 = "2026-09-20T10:00:00+08:00"
T2 = "2026-09-20T11:00:00+08:00"
T3 = "2026-09-21T09:00:00+08:00"
T4 = "2026-09-22T09:00:00+08:00"
FAR = "2027-09-20T09:00:00+08:00"


def signal(signal_id, source=WATCH, topic="topic-cooking", label="家常菜",
           at=T0, expires=FAR, **extra):
    payload = {
        "signal_id": signal_id,
        "source": source,
        "topic_id": topic,
        "label": label,
        "commercial": source == CAMPAIGN,
        "expires_at": expires,
    }
    if source == WATCH:
        payload["dwell_ms"] = extra.pop("dwell_ms", 30000)
    if source == SEARCH:
        payload["query"] = extra.pop("query", "菜谱")
    if source == FAVORITE:
        payload["target_id"] = extra.pop("target_id", "item-1")
    if source == NEGATIVE_FEEDBACK:
        payload["target_id"] = extra.pop("target_id", "item-1")
        payload["feedback_scope"] = extra.pop("feedback_scope", FEEDBACK_SCOPE_TOPIC)
    if source == CAMPAIGN:
        payload["campaign_id"] = extra.pop("campaign_id", "camp-1")
    payload.update(extra)
    return {
        "event_id": f"evt-{signal_id}",
        "kind": SIGNAL_OBSERVED,
        "occurred_at": at,
        "subject_id": "demo-001",
        "payload": payload,
    }


def interest(interest_id, source_signal_ids=("sig-1",), topic="topic-cooking",
             category="cat-food", sensitivity=SENSITIVITY_STANDARD, retention=RETENTION_LONG_TERM,
             commercial=False, aliases=(), at=T1, expires=FAR,
             policy_version="policy-v1", label="家常菜"):
    return {
        "event_id": f"evt-{interest_id}",
        "kind": "INTEREST_INFERRED",
        "occurred_at": at,
        "subject_id": "demo-001",
        "payload": {
            "interest_id": interest_id,
            "topic_id": topic,
            "label": label,
            "category": category,
            "aliases": list(aliases),
            "source_signal_ids": list(source_signal_ids),
            "sensitivity": sensitivity,
            "retention": retention,
            "commercial": commercial,
            "expires_at": expires,
            "policy_version": policy_version,
        },
    }


def boundary(change_id, action, target, at=T1, reason="用户操作", **extra):
    payload = {
        "change_id": change_id,
        "action": action,
        "target": target,
        "reason": reason,
        "effective_at": at,
    }
    payload.update(extra)
    return {
        "event_id": f"evt-{change_id}",
        "kind": "BOUNDARY_CHANGED",
        "occurred_at": at,
        "subject_id": "demo-001",
        "payload": payload,
    }


def access(decision_id, purpose, channel, signals=(), interests=(), at=T2,
           consumer="ranker", constraints=None, policy_version="policy-v1"):
    payload = {
        "access_id": f"acc-{decision_id}",
        "consumer": consumer,
        "policy_version": policy_version,
        "purpose": purpose,
        "channel": channel,
        "decision_id": decision_id,
        "used_signal_ids": list(signals),
        "used_interest_ids": list(interests),
    }
    if constraints is not None:
        payload["constraints"] = constraints
    return {
        "event_id": f"evt-{decision_id}",
        "kind": "PROFILE_ACCESSED",
        "occurred_at": at,
        "subject_id": "demo-001",
        "payload": payload,
    }


def withdrawal(withdrawal_id, targets, devices, caches, at=T3, status=WITHDRAWAL_PROPAGATED_STATUS,
               scope_type=SCOPE_SIGNAL, requested_at=T1):
    return {
        "event_id": f"evt-{withdrawal_id}",
        "kind": "WITHDRAWAL_PROPAGATED",
        "occurred_at": at,
        "subject_id": "demo-001",
        "payload": {
            "withdrawal_id": withdrawal_id,
            "requested_at": requested_at,
            "scope": {"type": scope_type, "id": targets[0]},
            "targets": list(targets),
            "devices": devices,
            "caches": caches,
            "status": status,
        },
    }


def acked(device_id, at):
    return {"device_id": device_id, "status": ACK_ACKED, "acked_at": at}


def evicted(scope, at):
    return {"cache_scope": scope, "status": CACHE_EVICTED,
            "evicted_at": at, "expires_at": FAR}


def expired(scope, at):
    return {"cache_scope": scope, "status": CACHE_EXPIRED,
            "evicted_at": None, "expires_at": at}


class EventShapeTest(unittest.TestCase):
    def test_unknown_kind_and_missing_fields_rejected(self):
        problems = validate_event({"kind": "NOPE"})
        self.assertIn("kind", problems)
        for name in ("event_id", "occurred_at", "subject_id", "payload"):
            self.assertIn(name, problems)

    def test_bad_timestamp_rejected(self):
        event = signal("sig-x", at="not-a-time")
        self.assertIn("occurred_at", validate_event(event))

    def test_each_signal_source_has_its_own_required_fields(self):
        self.assertEqual(validate_event(signal("s1", WATCH)), [])
        self.assertEqual(validate_event(signal("s2", SEARCH)), [])
        self.assertEqual(validate_event(signal("s3", FAVORITE)), [])
        self.assertEqual(validate_event(signal("s4", NEGATIVE_FEEDBACK)), [])
        self.assertEqual(validate_event(signal("s5", CAMPAIGN)), [])

        missing_scope = signal("s6", NEGATIVE_FEEDBACK)
        del missing_scope["payload"]["feedback_scope"]
        self.assertIn("payload.feedback_scope", validate_event(missing_scope))

    def test_negative_feedback_scope_must_be_explicit_item_topic_or_creator(self):
        bad = signal("s6", NEGATIVE_FEEDBACK, feedback_scope="ACCOUNT")
        self.assertIn("payload.feedback_scope", validate_event(bad))
        for scope in (FEEDBACK_SCOPE_ITEM, FEEDBACK_SCOPE_TOPIC, FEEDBACK_SCOPE_CREATOR):
            self.assertEqual(validate_event(signal("s", NEGATIVE_FEEDBACK, feedback_scope=scope)), [])


class InferenceInvariantTest(unittest.TestCase):
    def test_standard_long_term_interest_from_real_signals(self):
        history = [signal("sig-1", WATCH), signal("sig-2", SEARCH)]
        self.assertEqual(validate_event(interest("int-1", ["sig-1", "sig-2"]), history), [])

    def test_sensitive_topic_incidental_dwell_cannot_enter_long_term_profile(self):
        # 偶然停留（极短误触）单独存在时，敏感主题不得写入长期画像
        incidental = signal("sig-1", WATCH, topic="topic-sensitive-health",
                            dwell_ms= 800, incidental=True)
        event = interest("int-1", ["sig-1"], topic="topic-sensitive-health",
                         sensitivity=SENSITIVITY_SENSITIVE)
        self.assertIn("sensitive_long_term_without_corroboration",
                      validate_event(event, [incidental]))

    def test_sensitive_topic_session_retention_allowed_from_incidental_dwell(self):
        incidental = signal("sig-1", WATCH, topic="topic-sensitive-health",
                            dwell_ms=800, incidental=True)
        event = interest("int-1", ["sig-1"], topic="topic-sensitive-health",
                         sensitivity=SENSITIVITY_SENSITIVE, retention=RETENTION_SESSION)
        self.assertEqual(validate_event(event, [incidental]), [])

    def test_sensitive_long_term_allowed_with_explicit_corroboration(self):
        incidental = signal("sig-1", WATCH, topic="topic-sensitive-health",
                            dwell_ms=800, incidental=True)
        deliberate = signal("sig-2", FAVORITE, topic="topic-sensitive-health")
        event = interest("int-1", ["sig-1", "sig-2"],
                         topic="topic-sensitive-health", sensitivity=SENSITIVITY_SENSITIVE)
        self.assertEqual(validate_event(event, [incidental, deliberate]), [])

    def test_complete_watch_counts_as_corroboration(self):
        watch = signal("sig-1", WATCH, topic="topic-sensitive-health", dwell_ms=60000)
        event = interest("int-1", ["sig-1"], topic="topic-sensitive-health",
                         sensitivity=SENSITIVITY_SENSITIVE)
        self.assertEqual(validate_event(event, [watch]), [])

    def test_interest_must_cite_existing_valid_signals(self):
        event = interest("int-1", ["sig-missing"])
        self.assertTrue(any(p.startswith("unknown_source_signal:sig-missing")
                            for p in validate_event(event, [])))

    def test_expires_at_must_be_after_creation(self):
        event = interest("int-1", ["sig-1"], expires=T0)
        self.assertIn("expires_before_inferred",
                      validate_event(event, [signal("sig-1")]))


class BoundaryInvariantTest(unittest.TestCase):
    def test_suppression_blocks_topic_and_aliases(self):
        s1 = signal("sig-1", topic="topic-mukbang")
        change = boundary("chg-1", SUPPRESS,
                          {"type": SCOPE_TOPIC, "id": "topic-mukbang", "label": "吃播"},
                          aliases=["大胃王挑战", "速食比赛"])
        history = [s1, change]

        same_topic = interest("int-1", ["sig-1"], topic="topic-mukbang")
        self.assertIn("suppressed_alias_revival", validate_event(same_topic, history))

        alias_topic = interest("int-2", ["sig-1"], topic="大胃王挑战",
                               aliases=["topic-mukbang"])
        self.assertIn("suppressed_alias_revival", validate_event(alias_topic, history))

    def test_lifted_suppression_allows_new_inference_again(self):
        s1 = signal("sig-1", topic="topic-mukbang", at=T0)
        suppress = boundary("chg-1", SUPPRESS,
                            {"type": SCOPE_TOPIC, "id": "topic-mukbang"},
                            at=T1)
        lift = boundary("chg-2", LIFT_SUPPRESSION,
                        {"type": SCOPE_TOPIC, "id": "topic-mukbang"},
                        at=T3)
        new_signal = signal("sig-2", topic="topic-mukbang", at=T4)
        history = [s1, suppress, lift, new_signal]
        self.assertEqual(
            validate_event(interest("int-1", ["sig-2"], at=T4), history), [])

    def test_reset_cuts_off_pre_reset_signals(self):
        old1 = signal("sig-1", topic="topic-games", at=T0)
        old2 = signal("sig-2", SEARCH, topic="topic-games", at=T0)
        reset = boundary("chg-1", RESET,
                         {"type": SCOPE_TOPIC, "id": "topic-games"}, at=T1)
        # 重置后立刻用旧信号重建画像 -> 拒绝（旧策略借新事件复活）
        revived = interest("int-1", ["sig-1", "sig-2"], topic="topic-games", at=T2)
        problems = validate_event(revived, [old1, old2, reset])
        self.assertIn("pre_reset_signal:sig-1", problems)
        self.assertIn("pre_reset_signal:sig-2", problems)

        # 重置之后新产生的信号可以重新推断
        fresh = signal("sig-3", topic="topic-games", at=T3)
        self.assertEqual(
            validate_event(interest("int-2", ["sig-3"], at=T4),
                           [old1, old2, reset, fresh]),
            [])

    def test_account_reset_covers_other_categories(self):
        old = signal("sig-1", topic="topic-music")
        reset = boundary("chg-1", RESET, {"type": SCOPE_ACCOUNT, "id": "demo-001"}, at=T1)
        revived = interest("int-1", ["sig-1"], topic="topic-music",
                           category="cat-music", at=T2)
        self.assertIn("pre_reset_signal:sig-1",
                      validate_event(revived, [old, reset]))

    def test_category_reset_does_not_touch_other_categories(self):
        food = signal("sig-1", topic="topic-cooking", at=T0)
        music = signal("sig-2", topic="topic-music", at=T0)
        reset = boundary("chg-1", RESET,
                         {"type": SCOPE_CATEGORY, "id": "cat-food"}, at=T1)
        history = [food, music, reset]
        music_interest = interest("int-1", ["sig-2"], topic="topic-music",
                                  category="cat-music", at=T2)
        self.assertEqual(validate_event(music_interest, history), [])

    def test_limit_signal_kind_blocks_inference_from_that_kind(self):
        camp = signal("sig-1", CAMPAIGN, topic="topic-brand-x")
        limit = boundary("chg-1", LIMIT_INFERENCE,
                         {"type": SCOPE_SIGNAL_KIND, "id": CAMPAIGN},
                         enabled=True)
        event = interest("int-1", ["sig-1"], topic="topic-brand-x", commercial=True)
        self.assertIn("source_signal_kind_limited:sig-1",
                      validate_event(event, [camp, limit]))

        lifted = boundary("chg-2", LIMIT_INFERENCE,
                          {"type": SCOPE_SIGNAL_KIND, "id": CAMPAIGN},
                          at=T3, enabled=False)
        self.assertEqual(
            validate_event(interest("int-1", ["sig-1"], topic="topic-brand-x",
                                    commercial=True, at=T4),
                           [camp, limit, lifted]),
            [])

    def test_exploration_frequency_setting_requires_0_to_100(self):
        good = boundary("chg-1", "SET_EXPLORATION_FREQUENCY",
                        {"type": SCOPE_ACCOUNT, "id": "demo-001"},
                        constraints={"max_frequency_per_100": 10})
        self.assertEqual(validate_event(good), [])
        bad = boundary("chg-2", "SET_EXPLORATION_FREQUENCY",
                       {"type": SCOPE_ACCOUNT, "id": "demo-001"},
                       at=T2, constraints={"max_frequency_per_100": 120})
        self.assertIn("payload.constraints.max_frequency_per_100", validate_event(bad))

    def test_safety_boundary_setting_requires_version(self):
        bad = boundary("chg-1", "SET_SAFETY_BOUNDARY",
                       {"type": SCOPE_ACCOUNT, "id": "demo-001"})
        self.assertIn("payload.safety_boundary_version", validate_event(bad))
        good = boundary("chg-2", "SET_SAFETY_BOUNDARY",
                        {"type": SCOPE_ACCOUNT, "id": "demo-001"}, at=T2,
                        safety_boundary_version="safety-2026-07")
        self.assertEqual(validate_event(good), [])

    def test_suppression_target_must_be_topic(self):
        bad = boundary("chg-1", SUPPRESS,
                       {"type": SCOPE_ACCOUNT, "id": "demo-001"})
        self.assertIn("payload.target", validate_event(bad))


class AccessInvariantTest(unittest.TestCase):
    def setUp(self):
        self.history = [signal("sig-1", WATCH), signal("sig-2", SEARCH),
                        interest("int-1", ["sig-1", "sig-2"], at=T1)]

    def test_organic_rank_registers_policy_version_purpose_and_inputs(self):
        event = access("dec-1", PURPOSE_RANK_ORGANIC, CHANNEL_ORGANIC,
                       signals=["sig-1", "sig-2"], interests=["int-1"])
        self.assertEqual(validate_event(event, self.history), [])

    def test_purpose_and_channel_must_match(self):
        event = access("dec-1", PURPOSE_RANK_ADS, CHANNEL_ORGANIC,
                       signals=["sig-1"])
        self.assertIn("purpose_channel_mismatch", validate_event(event, self.history))

    def test_commercial_signal_must_not_enter_organic_recommendation(self):
        camp = signal("sig-9", CAMPAIGN, topic="topic-brand-x", at=T0)
        ad_interest = interest("int-9", ["sig-9"], topic="topic-brand-x",
                               commercial=True, at=T1)
        history = self.history + [camp, ad_interest]

        organic = access("dec-1", PURPOSE_RANK_ORGANIC, CHANNEL_ORGANIC,
                         signals=["sig-9"], interests=["int-9"])
        problems = validate_event(organic, history)
        self.assertIn("commercial_signal_in_organic:sig-9", problems)
        self.assertIn("commercial_interest_in_organic:int-9", problems)

        # 同一条投放画像在广告渠道可用
        ads = access("dec-2", PURPOSE_RANK_ADS, CHANNEL_ADS,
                     signals=["sig-9"], interests=["int-9"])
        self.assertEqual(validate_event(ads, history), [])

    def test_commercial_interest_origin_must_match_signals(self):
        camp = signal("sig-9", CAMPAIGN, topic="topic-brand-x")
        # 商业信号不能包装成自然兴趣
        disguised = interest("int-9", ["sig-9"], topic="topic-brand-x",
                             commercial=False)
        self.assertIn("commercial_origin_mismatch",
                      validate_event(disguised, [camp]))

    def test_exploration_requires_frequency_and_safety_constraints(self):
        bare = access("dec-1", PURPOSE_EXPLORATION, CHANNEL_ORGANIC)
        self.assertIn("exploration_constraints_required",
                      validate_event(bare, self.history))

    def test_exploration_must_obey_configured_frequency_and_safety(self):
        settings = [
            boundary("chg-1", "SET_EXPLORATION_FREQUENCY",
                     {"type": SCOPE_ACCOUNT, "id": "demo-001"},
                     at=T1, constraints={"max_frequency_per_100": 10}),
            boundary("chg-2", "SET_SAFETY_BOUNDARY",
                     {"type": SCOPE_ACCOUNT, "id": "demo-001"},
                     at=T1, safety_boundary_version="safety-2026-07"),
        ]
        history = self.history + settings

        ok = access("dec-1", PURPOSE_EXPLORATION, CHANNEL_ORGANIC, at=T2,
                    constraints={"max_frequency_per_100": 10,
                                 "safety_boundary_version": "safety-2026-07"})
        self.assertEqual(validate_event(ok, history), [])

        too_frequent = access("dec-2", PURPOSE_EXPLORATION, CHANNEL_ORGANIC, at=T2,
                              constraints={"max_frequency_per_100": 30,
                                           "safety_boundary_version": "safety-2026-07"})
        self.assertIn("exploration_frequency_mismatch",
                      validate_event(too_frequent, history))

        weaker_safety = access("dec-3", PURPOSE_EXPLORATION, CHANNEL_ORGANIC, at=T2,
                               constraints={"max_frequency_per_100": 10,
                                            "safety_boundary_version": "safety-2025-01"})
        self.assertIn("exploration_safety_mismatch",
                      validate_event(weaker_safety, history))

    def test_expired_signal_cannot_be_used(self):
        old = signal("sig-8", WATCH, at=T0, expires=T1)
        event = access("dec-1", PURPOSE_RANK_ORGANIC, CHANNEL_ORGANIC,
                       signals=["sig-8"], at=T3)
        self.assertIn("used_signal_not_valid:sig-8:EXPIRED",
                      validate_event(event, [old]))


class WithdrawalTest(unittest.TestCase):
    def _propagated_record(self, at=T3):
        return withdrawal(
            "wd-1", ["sig-1"],
            devices=[acked("dev-phone", T2), acked("dev-tablet", T2)],
            caches=[evicted("ranker:organic", T2), expired("exploration:organic", T2)],
            at=at,
        )

    def test_propagated_after_all_device_acks_and_cache_eviction_or_expiry(self):
        record = self._propagated_record()
        self.assertEqual(validate_event(record, []), [])
        state, reasons = evaluate_withdrawal(
            record, active_device_ids=["dev-phone", "dev-tablet"], at=T3)
        self.assertEqual(state, WITHDRAWAL_PROPAGATED_STATUS)
        self.assertEqual(reasons, [])

    def test_pending_when_one_active_device_has_not_acked(self):
        record = self._propagated_record()
        state, reasons = evaluate_withdrawal(
            record, active_device_ids=["dev-phone", "dev-tablet", "dev-watch"], at=T3)
        self.assertEqual(state, WITHDRAWAL_PENDING)
        self.assertIn("device_pending:dev-watch", reasons)

    def test_pending_when_cache_expiry_is_still_in_the_future(self):
        record = withdrawal(
            "wd-1", ["sig-1"],
            devices=[acked("dev-phone", T2)],
            caches=[{"cache_scope": "ranker:organic", "status": CACHE_EXPIRED,
                     "evicted_at": None, "expires_at": FAR}],
            at=T3,
        )
        state, reasons = evaluate_withdrawal(record, ["dev-phone"], at=T3)
        self.assertEqual(state, WITHDRAWAL_PENDING)
        self.assertIn("cache_pending:ranker:organic", reasons)

    def test_cache_that_expires_before_query_time_counts_as_done(self):
        record = withdrawal(
            "wd-1", ["sig-1"],
            devices=[acked("dev-phone", T2)],
            caches=[expired("ranker:organic", T2)],
            at=T3,
        )
        state, _ = evaluate_withdrawal(record, ["dev-phone"], at=T3)
        self.assertEqual(state, WITHDRAWAL_PROPAGATED_STATUS)

    def test_declared_propagated_event_must_match_actual_propagation(self):
        record = withdrawal(
            "wd-1", ["sig-1"],
            devices=[{"device_id": "dev-phone", "status": "PENDING"}],
            caches=[{"cache_scope": "ranker:organic", "status": CACHE_PENDING}],
            at=T3, status=WITHDRAWAL_PROPAGATED_STATUS,
        )
        self.assertIn("withdrawal_not_fully_propagated", validate_event(record, []))

    def test_future_ack_timestamp_is_not_yet_effective(self):
        record = withdrawal(
            "wd-1", ["sig-1"],
            devices=[{"device_id": "dev-phone", "status": ACK_ACKED,
                      "acked_at": FAR}],
            caches=[evicted("ranker:organic", T2)],
            at=T3,
        )
        self.assertIn("device_ack_time:dev-phone", validate_event(record, []))

    def test_withdrawn_signal_excluded_from_new_decisions(self):
        s1 = signal("sig-1", at=T0)
        wd = self._propagated_record(at=T3)
        history = [s1, wd]
        event = access("dec-1", PURPOSE_RANK_ORGANIC, CHANNEL_ORGANIC,
                       signals=["sig-1"], at=T4)
        self.assertIn("used_signal_not_valid:sig-1:WITHDRAWN",
                      validate_event(event, history))

    def test_derived_interest_inherits_source_withdrawal(self):
        # 信号撤回后，仅由它派生的兴趣条目在新决策中同样失效，
        # 避免画像通过“派生条目”这条别名路径重新参与决策
        s1 = signal("sig-1", at=T0)
        i1 = interest("int-1", ["sig-1"], at=T1)
        wd = withdrawal("wd-1", ["sig-1"],
                        devices=[acked("dev-phone", T2)],
                        caches=[evicted("ranker:organic", T2)],
                        at=T3)
        history = [s1, i1, wd]
        event = access("dec-1", PURPOSE_RANK_ORGANIC, CHANNEL_ORGANIC,
                       interests=["int-1"], at=T4)
        self.assertIn("used_interest_not_valid:int-1:WITHDRAWN",
                      validate_event(event, history))

        # 只要派生依据中包含被撤回信号，条目就必须剔除该信号后重新推断，
        # 不能带旧依据继续参与决策
        s2 = signal("sig-2", SEARCH, at=T0)
        i2 = interest("int-2", ["sig-1", "sig-2"], at=T1)
        stale = access("dec-2", PURPOSE_RANK_ORGANIC, CHANNEL_ORGANIC,
                       interests=["int-2"], at=T4)
        self.assertIn("used_interest_not_valid:int-2:WITHDRAWN",
                      validate_event(stale, [s1, s2, i2, wd]))

        i3 = interest("int-3", ["sig-2"], at=T3)
        rederived = access("dec-3", PURPOSE_RANK_ORGANIC, CHANNEL_ORGANIC,
                           signals=["sig-2"], interests=["int-3"], at=T4)
        self.assertEqual(
            validate_event(rederived, [s1, s2, i2, wd, i3]), [])

    def test_withdrawn_interest_excluded_but_signal_scope_does_not_collide(self):
        s1 = signal("sig-1", at=T0)
        i1 = interest("int-1", ["sig-1"], at=T1)
        # 撤回一个“恰好同名”的兴趣 id，不应波及信号
        wd_interest = withdrawal("wd-1", ["sig-1"],
                                 devices=[acked("dev-phone", T2)],
                                 caches=[evicted("ranker:organic", T2)],
                                 at=T3, scope_type=SCOPE_INTEREST)
        history = [s1, i1, wd_interest]
        event = access("dec-1", PURPOSE_RANK_ORGANIC, CHANNEL_ORGANIC,
                       signals=["sig-1"], at=T4)
        self.assertEqual(validate_event(event, history), [])

        # 信号级撤回才让信号失效
        wd_signal = withdrawal("wd-2", ["sig-1"],
                               devices=[acked("dev-phone", T2)],
                               caches=[evicted("ranker:organic", T2)],
                               at=T4, scope_type=SCOPE_SIGNAL)
        problems = validate_event(
            access("dec-2", PURPOSE_RANK_ORGANIC, CHANNEL_ORGANIC,
                   signals=["sig-1"], at="2026-09-23T09:00:00+08:00"),
            history + [wd_signal])
        self.assertIn("used_signal_not_valid:sig-1:WITHDRAWN", problems)


class CustomerServiceExplanationTest(unittest.TestCase):
    def test_explanation_shows_each_signal_with_validity_at_decision_and_query(self):
        s1 = signal("sig-1", WATCH, at=T0)
        s2 = signal("sig-2", SEARCH, at=T0)
        i1 = interest("int-1", ["sig-1", "sig-2"], at=T1)
        decision = access("dec-1", PURPOSE_RANK_ORGANIC, CHANNEL_ORGANIC,
                          signals=["sig-1", "sig-2"], interests=["int-1"],
                          at=T2, consumer="organic-feed-ranker")
        wd = withdrawal(
            "wd-1", ["sig-1"],
            devices=[acked("dev-phone", T3)],
            caches=[evicted("ranker:organic", T3)],
            at=T3,
        )
        history = [s1, s2, i1, decision, wd]

        explanation = explain_decision(history, "dec-1", at=T4)
        self.assertEqual(explanation["policy_version"], "policy-v1")
        self.assertEqual(explanation["channel"], CHANNEL_ORGANIC)
        self.assertEqual(explanation["purpose"], PURPOSE_RANK_ORGANIC)
        by_id = {row["signal_id"]: row for row in explanation["signals"]}

        # 决策发生在撤回前：当时两条信号都有效；客服查询时 sig-1 已撤回
        self.assertEqual(by_id["sig-1"]["status_at_decision"], VALID)
        self.assertEqual(by_id["sig-1"]["status_at_query"], WITHDRAWN)
        self.assertEqual(by_id["sig-2"]["status_at_query"], VALID)
        self.assertFalse(by_id["sig-1"]["commercial"])
        # 人类化字段：可读名称、来源、有效期都可解释
        self.assertEqual(by_id["sig-1"]["label"], "家常菜")
        self.assertEqual(by_id["sig-1"]["source"], WATCH)
        self.assertEqual(by_id["sig-1"]["expires_at"], FAR)

        interest_row = explanation["interests"][0]
        self.assertEqual(interest_row["status_at_decision"], VALID)
        self.assertEqual(interest_row["aliases"], [])

    def test_explanation_unknown_decision_raises(self):
        with self.assertRaises(ValueError):
            explain_decision([], "dec-nope")

    def test_suppressed_interest_status_visible_in_explanation(self):
        s1 = signal("sig-1", topic="topic-mukbang", at=T0)
        i1 = interest("int-1", ["sig-1"], topic="topic-mukbang", at=T1)
        decision = access("dec-1", PURPOSE_RANK_ORGANIC, CHANNEL_ORGANIC,
                          signals=["sig-1"], interests=["int-1"], at=T2)
        suppress = boundary("chg-1", SUPPRESS,
                            {"type": SCOPE_TOPIC, "id": "topic-mukbang"}, at=T3)
        history = [s1, i1, decision, suppress]
        explanation = explain_decision(history, "dec-1", at=T4)
        row = explanation["interests"][0]
        self.assertEqual(row["status_at_decision"], VALID)
        self.assertEqual(row["status_at_query"], SUPPRESSED)


class ReadableProfileTest(unittest.TestCase):
    def test_profile_lists_readable_entries_with_sources_and_expiry_split_by_channel(self):
        history = [
            signal("sig-1", WATCH, at=T0),
            signal("sig-2", SEARCH, at=T0),
            signal("sig-3", CAMPAIGN, topic="topic-brand-x", at=T0),
            interest("int-1", ["sig-1", "sig-2"], at=T1),
            interest("int-2", ["sig-3"], topic="topic-brand-x",
                     commercial=True, retention=RETENTION_SESSION, at=T1),
        ]
        view = readable_profile(history, at=T2)
        self.assertEqual([row["interest_id"] for row in view["organic_interests"]], ["int-1"])
        self.assertEqual([row["interest_id"] for row in view["ad_interests"]], ["int-2"])

        row = view["organic_interests"][0]
        self.assertEqual(row["label"], "家常菜")
        self.assertEqual(row["expires_at"], FAR)
        self.assertEqual(row["sensitivity"], SENSITIVITY_STANDARD)
        self.assertEqual(row["retention"], RETENTION_LONG_TERM)
        sources = {s["signal_id"]: s["source"] for s in row["sources"]}
        self.assertEqual(sources, {"sig-1": WATCH, "sig-2": SEARCH})

    def test_profile_hides_expired_withdrawn_and_suppressed_entries(self):
        history = [
            signal("sig-1", topic="topic-cooking", at=T0),
            signal("sig-2", topic="topic-mukbang", at=T0),
            interest("int-1", ["sig-1"], topic="topic-cooking", at=T1),
            interest("int-2", ["sig-2"], topic="topic-mukbang", at=T1),
            boundary("chg-1", SUPPRESS,
                     {"type": SCOPE_TOPIC, "id": "topic-mukbang"}, at=T2),
            withdrawal("wd-1", ["int-1"],
                       devices=[acked("dev-phone", T2)],
                       caches=[evicted("ranker:organic", T2)],
                       at=T3, scope_type=SCOPE_INTEREST),
        ]
        view = readable_profile(history, at=T4)
        self.assertEqual(view["organic_interests"], [])
        self.assertEqual(view["ad_interests"], [])


class EventKindCoverageTest(unittest.TestCase):
    def test_five_domain_event_kinds_remain_stable(self):
        self.assertEqual(
            EVENT_KINDS,
            ["SIGNAL_OBSERVED", "INTEREST_INFERRED", "BOUNDARY_CHANGED",
             "PROFILE_ACCESSED", "WITHDRAWAL_PROPAGATED"],
        )


if __name__ == "__main__":
    unittest.main()
