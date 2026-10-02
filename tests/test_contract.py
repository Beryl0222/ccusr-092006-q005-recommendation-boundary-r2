import json
import unittest
from pathlib import Path

from src.recommendation_boundary import validate_event

ROOT = Path(__file__).parents[1]


class ContractTest(unittest.TestCase):
    def test_sample_matches_domain_contract(self):
        record = json.loads((ROOT / "data" / "sample.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_event(record), [])

    def test_sample_timeline_is_consistent_when_replayed_in_order(self):
        timeline = json.loads(
            (ROOT / "data" / "sample_timeline.json").read_text(encoding="utf-8")
        )
        history = []
        for event in timeline:
            problems = validate_event(event, history)
            self.assertEqual(problems, [], f"{event['event_id']}: {problems}")
            history.append(event)


if __name__ == "__main__":
    unittest.main()
