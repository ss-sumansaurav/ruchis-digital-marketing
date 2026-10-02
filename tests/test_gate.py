import tempfile
import unittest
from pathlib import Path

from agency import ApprovalError, Engagement, MockAdapter, SpendBlocked

KEY = "principal-secret"
TODAY = "2026-11-05"


class GateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.eng = Engagement.create(Path(self.dir.name) / "acme.json", "acme", "INR", 500_000)
        self.eng.set_key(KEY)
        self.adapter = MockAdapter()

    def tearDown(self):
        self.dir.cleanup()

    def request(self, amount=200_000, campaign="*", channel="paid_search", cap=8_000):
        return self.eng.create_request(campaign=campaign, channel=channel, amount=amount,
                                       start="2026-11-01", end="2026-11-30", daily_cap=cap, summary="test")

    def launch(self, rid, name="brand", budget=100_000, daily=4_000, channel="paid_search", **extra):
        action = {"type": "launch", "request_id": rid, "campaign": name, "channel": channel,
                  "budget": budget, "daily_budget": daily, **extra}
        return self.eng.execute(action, self.adapter, today=TODAY)

    def approved(self, **kw):
        rid = self.request(**kw)
        self.eng.approve(rid, KEY)
        return rid

    # --- nothing launches without a recorded approval
    def test_launch_without_any_request_is_blocked(self):
        with self.assertRaises(SpendBlocked):
            self.launch(None)
        self.assertEqual(self.adapter.calls, [])

    def test_launch_on_pending_request_is_blocked(self):
        with self.assertRaises(SpendBlocked):
            self.launch(self.request())
        self.assertEqual(self.adapter.calls, [])

    def test_launch_on_rejected_request_is_blocked(self):
        rid = self.request()
        self.eng.reject(rid, KEY, "too expensive")
        with self.assertRaises(SpendBlocked):
            self.launch(rid)

    # --- only the Principal can approve
    def test_wrong_key_cannot_approve(self):
        rid = self.request()
        with self.assertRaises(ApprovalError):
            self.eng.approve(rid, "guess")
        self.assertEqual(self.eng.data["requests"][rid]["status"], "PENDING")

    def test_key_is_not_stored_in_plain_text(self):
        self.assertNotIn(KEY, self.eng.path.read_text())

    # --- an approval covers only what it states
    def test_approved_launch_within_scope_runs(self):
        self.launch(self.approved())
        self.assertEqual(len(self.adapter.calls), 1)
        self.assertEqual(self.eng.ledger()["committed"], 100_000)

    def test_over_approved_amount_is_blocked(self):
        rid = self.approved()
        self.launch(rid, "brand", 150_000)
        with self.assertRaises(SpendBlocked):
            self.launch(rid, "generic", 60_000)

    def test_over_daily_cap_is_blocked(self):
        with self.assertRaises(SpendBlocked):
            self.launch(self.approved(), daily=9_000)

    def test_wrong_channel_is_blocked(self):
        with self.assertRaises(SpendBlocked):
            self.launch(self.approved(), channel="paid_social")

    def test_wrong_campaign_is_blocked(self):
        with self.assertRaises(SpendBlocked):
            self.launch(self.approved(campaign="brand"), name="generic")

    def test_flight_outside_approved_dates_is_blocked(self):
        with self.assertRaises(SpendBlocked):
            self.launch(self.approved(), end="2026-12-15")

    def test_expired_approval_is_blocked(self):
        rid = self.approved()
        action = {"type": "launch", "request_id": rid, "campaign": "brand", "channel": "paid_search",
                  "budget": 1_000, "daily_budget": 100}
        with self.assertRaises(SpendBlocked):
            self.eng.execute(action, self.adapter, today="2026-12-01")

    def test_modified_approval_limits_to_the_modified_amount(self):
        rid = self.request()
        self.eng.approve(rid, KEY, amount=50_000)
        with self.assertRaises(SpendBlocked):
            self.launch(rid, budget=100_000)
        self.launch(rid, budget=50_000)

    # --- changes after launch
    def test_increase_beyond_approval_blocked_and_within_allowed(self):
        rid = self.approved()
        self.launch(rid)
        up = {"type": "increase_budget", "campaign": "brand", "budget": 250_000}
        with self.assertRaises(SpendBlocked):
            self.eng.execute(up, self.adapter, today=TODAY)
        self.eng.execute({**up, "budget": 180_000}, self.adapter, today=TODAY)
        self.assertEqual(self.eng.data["campaigns"]["brand"]["budget"], 180_000)

    def test_extend_flight_beyond_approval_is_blocked(self):
        rid = self.approved()
        self.launch(rid, end="2026-11-20")
        with self.assertRaises(SpendBlocked):
            self.eng.execute({"type": "extend_flight", "campaign": "brand", "end": "2026-12-10"},
                             self.adapter, today=TODAY)

    def test_pause_and_decrease_never_need_approval(self):
        self.launch(self.approved())
        self.eng.execute({"type": "decrease_budget", "campaign": "brand", "budget": 40_000}, self.adapter)
        self.eng.execute({"type": "pause", "campaign": "brand"}, self.adapter)
        camp = self.eng.data["campaigns"]["brand"]
        self.assertEqual((camp["budget"], camp["status"]), (40_000, "paused"))

    def test_decrease_cannot_be_used_to_raise_budget(self):
        self.launch(self.approved())
        with self.assertRaises(SpendBlocked):
            self.eng.execute({"type": "decrease_budget", "campaign": "brand", "budget": 400_000}, self.adapter)

    def test_unknown_action_type_is_refused(self):
        with self.assertRaises(SpendBlocked):
            self.eng.execute({"type": "boost", "campaign": "brand"}, self.adapter)

    # --- the client ceiling
    def test_request_over_ceiling_is_refused(self):
        with self.assertRaises(ApprovalError):
            self.request(amount=600_000)

    def test_approvals_cannot_add_up_past_ceiling(self):
        a, b = self.request(amount=300_000), self.request(amount=300_000, channel="paid_social")
        self.eng.approve(a, KEY)
        with self.assertRaises(ApprovalError):
            self.eng.approve(b, KEY)

    # --- ledger and audit
    def test_ledger_and_audit_trail(self):
        rid = self.approved()
        self.launch(rid)
        self.eng.record_spend("brand", 12_500, "2026-11-05")
        led = self.eng.ledger()
        self.assertEqual((led["approved"], led["committed"], led["spent"], led["remaining_of_ceiling"]),
                         (200_000, 100_000, 12_500, 487_500))
        with self.assertRaises(SpendBlocked):
            self.launch(rid, "x", channel="display")
        audit = self.eng.path.with_suffix(".audit.jsonl").read_text()
        for event in ("request_created", "request_approved", "action_executed", "spend_recorded", "action_blocked"):
            self.assertIn(event, audit)


if __name__ == "__main__":
    unittest.main()
