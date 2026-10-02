"""Telegram approvals: only the bound Principal account, with the bot's secret and the live message, can decide."""
import tempfile
import unittest
from pathlib import Path

from agency import ApprovalError, Engagement
from agency.telegram import ApprovalBot, FakeAPI, format_request

KEY = "principal-secret"
RUCHI, CHAT, STRANGER = 111111, 222222, 999999


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = Path(self.dir.name)
        self.eng = Engagement.create(self.state / "acme.json", "acme", "INR", 500_000)
        self.eng.set_key(KEY)
        self.secret = self.eng.bind_channel(KEY, "telegram", RUCHI, CHAT)
        self.rid = self.eng.create_request(campaign="*", channel="paid_search", amount=200_000, start="2026-11-01",
                                           end="2026-11-30", daily_cap=8_000, summary="Search envelope",
                                           detail={"objective": "Sales; primary KPI backend CPA, target ₹900"})
        self.api = FakeAPI()
        self.bot = ApprovalBot(self.state, self.api, self.secret)

    def tearDown(self):
        self.dir.cleanup()

    def fresh(self):
        return Engagement(self.state / "acme.json").data["requests"][self.rid]

    def sent_buttons(self):
        markup = [p for m, p in self.api.calls if m == "sendMessage" and "reply_markup" in p][-1]["reply_markup"]
        return {b["text"]: b["callback_data"] for b in markup["inline_keyboard"][0]}

    def press(self, data, user=RUCHI):
        return self.bot.handle({"callback_query": {"id": "q", "from": {"id": user}, "data": data,
                                                   "message": {"message_id": 1, "chat": {"id": CHAT}}}})

    def say(self, text, user=RUCHI):
        return self.bot.handle({"message": {"text": text, "from": {"id": user}, "chat": {"id": CHAT}}})

    # --- sending
    def test_bot_sends_pending_requests_to_the_bound_chat_only_once(self):
        self.assertEqual(self.bot.send_pending(), [f"acme/{self.rid}"])
        self.assertEqual(self.bot.send_pending(), [])
        send = [p for m, p in self.api.calls if m == "sendMessage"]
        self.assertEqual(len(send), 1)
        self.assertEqual(send[0]["chat_id"], CHAT)
        self.assertIn("₹200,000", send[0]["text"])
        self.assertIn("backend CPA", send[0]["text"])

    def test_message_carries_the_budget_position(self):
        text = format_request(self.eng, self.rid)
        self.assertIn("ceiling ₹500,000", text)
        self.assertIn("headroom after this ₹300,000", text)

    def test_nothing_is_sent_without_a_bound_account(self):
        other = Engagement.create(self.state / "beta.json", "beta", "INR", 100_000)
        other.create_request(campaign="*", channel="paid_social", amount=10_000, start="2026-11-01",
                             end="2026-11-30", daily_cap=500, summary="x")
        self.assertEqual(self.bot.send_pending(), [f"acme/{self.rid}"])

    # --- deciding
    def test_ruchi_approves_with_the_button(self):
        self.bot.send_pending()
        result = self.press(self.sent_buttons()["APPROVE"])
        self.assertIn("APPROVED", result)
        self.assertEqual(self.fresh()["status"], "APPROVED")
        self.assertEqual(self.fresh()["approved_amount"], 200_000)

    def test_ruchi_rejects_with_the_button(self):
        self.bot.send_pending()
        self.press(self.sent_buttons()["REJECT"])
        self.assertEqual(self.fresh()["status"], "REJECTED")

    def test_anyone_else_pressing_the_button_is_refused(self):
        self.bot.send_pending()
        result = self.press(self.sent_buttons()["APPROVE"], user=STRANGER)
        self.assertIn("Not recorded", result)
        self.assertEqual(self.fresh()["status"], "PENDING")

    def test_without_the_bot_secret_nothing_is_recorded(self):
        self.bot.send_pending()
        forged = ApprovalBot(self.state, FakeAPI(), "guessed-secret")
        forged.handle({"callback_query": {"id": "q", "from": {"id": RUCHI}, "data": self.sent_buttons()["APPROVE"]}})
        self.assertEqual(self.fresh()["status"], "PENDING")

    def test_an_old_or_invented_message_is_refused(self):
        self.bot.send_pending()
        self.press(f"a:acme:{self.rid}:deadbeef")
        self.assertEqual(self.fresh()["status"], "PENDING")

    def test_a_button_works_once(self):
        self.bot.send_pending()
        data = self.sent_buttons()["APPROVE"]
        self.press(data)
        self.assertIn("Not recorded", self.press(data))

    def test_modify_can_lower_the_amount_and_cap(self):
        self.bot.send_pending()
        result = self.say(f"MODIFY {self.rid} 150000 6000")
        self.assertIn("APPROVED as modified", result)
        r = self.fresh()
        self.assertEqual((r["status"], r["approved_amount"], r["daily_cap"]), ("APPROVED", 150_000, 6_000))

    def test_modify_cannot_raise_from_telegram(self):
        self.bot.send_pending()
        self.assertIn("Not recorded", self.say(f"MODIFY {self.rid} 250000"))
        self.assertIn("Not recorded", self.say(f"MODIFY {self.rid} 200000 9000"))
        self.assertEqual(self.fresh()["status"], "PENDING")

    def test_modify_from_a_stranger_is_refused(self):
        self.bot.send_pending()
        self.assertIn("Not recorded", self.say(f"MODIFY {self.rid} 100000", user=STRANGER))
        self.assertEqual(self.fresh()["status"], "PENDING")

    def test_reject_by_text_keeps_the_reason(self):
        self.bot.send_pending()
        self.say(f"REJECT {self.rid} wait for new creative")
        self.assertEqual((self.fresh()["status"], self.fresh()["note"]), ("REJECTED", "wait for new creative"))

    def test_silence_is_not_approval(self):
        self.bot.send_pending()
        self.say("ok sounds good")
        self.assertEqual(self.fresh()["status"], "PENDING")

    def test_binding_needs_the_principal_key(self):
        with self.assertRaises(ApprovalError):
            self.eng.bind_channel("wrong-key", "telegram", STRANGER, STRANGER)

    def test_start_tells_ruchi_her_ids(self):
        self.assertIn(str(RUCHI), self.say("/start"))

    def test_decisions_are_audited_with_the_channel(self):
        self.bot.send_pending()
        self.press(self.sent_buttons()["APPROVE"], user=STRANGER)
        self.press(self.sent_buttons()["APPROVE"])
        log = (self.state / "acme.audit.jsonl").read_text()
        self.assertIn("decision_refused_channel_auth", log)
        self.assertIn('"via": "telegram"', log)


if __name__ == "__main__":
    unittest.main()
