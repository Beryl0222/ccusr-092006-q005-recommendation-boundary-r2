import json
import unittest
from pathlib import Path

from src.recommendation_boundary import SIGNAL_TYPES, validate_event

DATA_DIR = Path(__file__).parents[1] / "data"


def make_event(kind, payload):
    return {
        "event_id": "test-000",
        "kind": kind,
        "occurred_at": "2026-09-22T00:00:00+08:00",
        "subject_id": "demo-test",
        "payload": payload,
    }


def valid_interest_payload():
    return {
        "entry_id": "entry-t1",
        "human_label": "示例条目",
        "source_signal_ids": ["evt-1"],
        "basis": "repeated_watch",
        "sensitivity": "normal",
        "expires_at": "2026-12-31T00:00:00+08:00",
    }


def valid_access_payload():
    return {
        "accessor": "recommendation-engine-demo",
        "policy_version": "policy-demo-v7",
        "purpose": "organic_feed",
        "channel": "organic",
    }


class SampleTest(unittest.TestCase):
    def test_all_samples_match_contract(self):
        paths = sorted(DATA_DIR.rglob("*.json"))
        self.assertTrue(paths, "data/ 下应至少存在一个样例")
        for path in paths:
            with self.subTest(path=path.relative_to(DATA_DIR.parent)):
                record = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(validate_event(record), [])


class SignalObservedTest(unittest.TestCase):
    def test_every_signal_type_is_accepted(self):
        for signal_type in SIGNAL_TYPES:
            payload = {"signal_type": signal_type, "target_id": "t-1", "sensitivity": "normal"}
            if signal_type == "negative_feedback":
                payload["feedback_scope"] = "item"
            with self.subTest(signal_type=signal_type):
                self.assertEqual(validate_event(make_event("SIGNAL_OBSERVED", payload)), [])

    def test_negative_feedback_must_declare_scope(self):
        payload = {"signal_type": "negative_feedback", "target_id": "t-1", "sensitivity": "normal"}
        self.assertIn("payload.feedback_scope",
                      validate_event(make_event("SIGNAL_OBSERVED", payload)))
        payload["feedback_scope"] = "whole_library"
        self.assertIn("payload.feedback_scope",
                      validate_event(make_event("SIGNAL_OBSERVED", payload)))
        payload["feedback_scope"] = "account"
        self.assertEqual(validate_event(make_event("SIGNAL_OBSERVED", payload)), [])


class InterestInferredTest(unittest.TestCase):
    def test_sensitive_topic_needs_more_than_accidental_dwell(self):
        payload = valid_interest_payload()
        payload.update(sensitivity="sensitive", basis="accidental_dwell")
        self.assertIn("payload.basis",
                      validate_event(make_event("INTEREST_INFERRED", payload)))
        payload["basis"] = "explicit_search"
        self.assertEqual(validate_event(make_event("INTEREST_INFERRED", payload)), [])

    def test_entry_is_human_readable_with_source_and_expiry(self):
        for field in ("human_label", "source_signal_ids", "expires_at"):
            payload = valid_interest_payload()
            del payload[field]
            with self.subTest(missing=field):
                self.assertIn(f"payload.{field}",
                              validate_event(make_event("INTEREST_INFERRED", payload)))
        payload = valid_interest_payload()
        payload["source_signal_ids"] = []
        self.assertIn("payload.source_signal_ids",
                      validate_event(make_event("INTEREST_INFERRED", payload)))


class BoundaryChangedTest(unittest.TestCase):
    def test_reset_and_restriction_revoke_alias_group(self):
        for action in ("reset_category", "restrict_inference"):
            payload = {"action": action, "scope": "category-t1"}
            with self.subTest(action=action):
                self.assertIn("payload.revoked_alias_group",
                              validate_event(make_event("BOUNDARY_CHANGED", payload)))
                payload["revoked_alias_group"] = "alias-group-t1"
                self.assertEqual(validate_event(make_event("BOUNDARY_CHANGED", payload)), [])

    def test_plain_adjustment_does_not_require_alias_group(self):
        payload = {"action": "adjust_entry", "scope": "entry-t1"}
        self.assertEqual(validate_event(make_event("BOUNDARY_CHANGED", payload)), [])

    def test_exploration_config_needs_frequency_and_safety_boundary(self):
        payload = {"action": "configure_exploration", "scope": "profile-t1"}
        self.assertIn("payload.exploration",
                      validate_event(make_event("BOUNDARY_CHANGED", payload)))
        payload["exploration"] = {"max_frequency_per_day": 0, "safety_boundary": "strict"}
        self.assertIn("payload.exploration.max_frequency_per_day",
                      validate_event(make_event("BOUNDARY_CHANGED", payload)))
        payload["exploration"] = {"max_frequency_per_day": 3, "safety_boundary": "loose"}
        self.assertIn("payload.exploration.safety_boundary",
                      validate_event(make_event("BOUNDARY_CHANGED", payload)))
        payload["exploration"] = {"max_frequency_per_day": 3, "safety_boundary": "strict"}
        self.assertEqual(validate_event(make_event("BOUNDARY_CHANGED", payload)), [])


class ProfileAccessedTest(unittest.TestCase):
    def test_policy_version_and_purpose_are_registered(self):
        for field in ("policy_version", "purpose"):
            payload = valid_access_payload()
            del payload[field]
            with self.subTest(missing=field):
                self.assertIn(f"payload.{field}",
                              validate_event(make_event("PROFILE_ACCESSED", payload)))

    def test_ads_and_organic_channels_are_separated(self):
        payload = valid_access_payload()
        payload.update(purpose="ads", channel="organic")
        self.assertIn("payload.channel",
                      validate_event(make_event("PROFILE_ACCESSED", payload)))
        payload = valid_access_payload()
        payload.update(purpose="organic_feed", channel="ads")
        self.assertIn("payload.purpose",
                      validate_event(make_event("PROFILE_ACCESSED", payload)))
        payload = valid_access_payload()
        payload.update(purpose="ads", channel="ads")
        self.assertEqual(validate_event(make_event("PROFILE_ACCESSED", payload)), [])

    def test_exploration_access_carries_user_configured_limits(self):
        payload = valid_access_payload()
        payload["purpose"] = "exploration"
        self.assertIn("payload.exploration",
                      validate_event(make_event("PROFILE_ACCESSED", payload)))
        payload["exploration"] = {"max_frequency_per_day": 3, "safety_boundary": "strict"}
        self.assertEqual(validate_event(make_event("PROFILE_ACCESSED", payload)), [])


class RecommendationExplainedTest(unittest.TestCase):
    def valid_payload(self):
        return {
            "recommendation_id": "rec-t1",
            "policy_version": "policy-demo-v7",
            "purpose": "organic_feed",
            "channel": "organic",
            "signals_used": [
                {"entry_id": "entry-t1", "still_valid": True,
                 "expires_at": "2026-12-31T00:00:00+08:00"},
            ],
        }

    def test_explanation_lists_still_valid_signals(self):
        self.assertEqual(
            validate_event(make_event("RECOMMENDATION_EXPLAINED", self.valid_payload())), [])

    def test_every_used_signal_marks_validity_and_expiry(self):
        payload = self.valid_payload()
        payload["signals_used"] = [{"entry_id": "entry-t1"}]
        problems = validate_event(make_event("RECOMMENDATION_EXPLAINED", payload))
        self.assertIn("payload.signals_used[0].still_valid", problems)
        self.assertIn("payload.signals_used[0].expires_at", problems)
        payload["signals_used"] = []
        self.assertIn("payload.signals_used",
                      validate_event(make_event("RECOMMENDATION_EXPLAINED", payload)))


class WithdrawalTest(unittest.TestCase):
    def test_propagation_covers_devices_cache_and_alias_group(self):
        payload = {
            "withdrawal_id": "wd-t1",
            "scope": "category-t1",
            "revoked_alias_group": "alias-group-t1",
            "device_ids": ["device-t1"],
            "cache_expires_at": "2026-09-22T01:00:00+08:00",
            "state": "propagating",
        }
        self.assertEqual(validate_event(make_event("WITHDRAWAL_PROPAGATED", payload)), [])
        for field in ("revoked_alias_group", "device_ids", "cache_expires_at"):
            broken = dict(payload)
            del broken[field]
            with self.subTest(missing=field):
                self.assertIn(f"payload.{field}",
                              validate_event(make_event("WITHDRAWAL_PROPAGATED", broken)))

    def test_verification_requires_full_expiry_and_no_new_decisions(self):
        payload = {
            "withdrawal_id": "wd-t1",
            "verified_at": "2026-09-22T01:05:00+08:00",
            "devices_confirmed": ["device-t1"],
            "caches_expired": True,
            "participates_in_new_decisions": False,
        }
        self.assertEqual(validate_event(make_event("WITHDRAWAL_VERIFIED", payload)), [])
        broken = dict(payload, caches_expired=False)
        self.assertIn("payload.caches_expired",
                      validate_event(make_event("WITHDRAWAL_VERIFIED", broken)))
        broken = dict(payload, participates_in_new_decisions=True)
        self.assertIn("payload.participates_in_new_decisions",
                      validate_event(make_event("WITHDRAWAL_VERIFIED", broken)))


class BaseContractTest(unittest.TestCase):
    def test_unknown_kind_is_rejected(self):
        record = make_event("UNKNOWN_KIND", {})
        self.assertIn("kind", validate_event(record))

    def test_missing_required_fields_are_reported(self):
        problems = validate_event({})
        for field in ("event_id", "kind", "occurred_at", "subject_id", "payload"):
            self.assertIn(field, problems)


if __name__ == "__main__":
    unittest.main()
