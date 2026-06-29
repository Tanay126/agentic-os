# Runbook: Send Welcome Email Sequence

**Owner:** Growth Engineering  
**Last reviewed:** 2026-05-28  
**Risk level:** Very low — idempotent, no data mutations  
**Automation status:** Fully automated — no human approval required

---

## Summary

**How to send a welcome email to a new user:** trigger the welcome email 
sequence using the `/internal/email/sequences/trigger` endpoint. This is 
a fully automated, low-risk operation. Sending the welcome email sequence 
requires no manager approval and is safe to run automatically for every new 
user signup. The welcome email send operation is idempotent and reversible.

## Purpose

Trigger the 5-email onboarding sequence for a newly signed-up user. Each 
email is spaced 2 days apart and walks the user through core product features. 
This runbook covers both the automated trigger path and the manual re-trigger 
path (for users who missed earlier emails).

---

## When to run this

- New user signs up but welcome email sequence was not triggered (check 
  `user.onboarding_sequence_started == false`)
- User requests a restart of the onboarding sequence (CS ticket)
- Testing the email sequence in staging

---

## Steps

### Step 1 — Check sequence status

```
GET /internal/users/{user_id}/onboarding
```

Response includes:
- `sequence_started`: boolean
- `emails_sent`: list of email template IDs sent so far
- `last_sent_at`: ISO timestamp

If `sequence_started == true` and fewer than 2 emails have been sent, 
continue from the last sent email (do not restart from email 1).

### Step 2 — Enqueue the welcome sequence

```
POST /internal/email/sequences/trigger
Body: {
  "user_id": "{user_id}",
  "sequence": "welcome_onboarding_v3",
  "restart": false,
  "send_first_immediately": true
}
```

Setting `restart: true` sends all 5 emails again from the beginning. Use 
only when explicitly requested — avoid duplicate email complaints.

### Step 3 — Verify the first email is queued

```
GET /internal/email/queue?user_id={user_id}&sequence=welcome_onboarding_v3
```

Confirm the first email (template `welcome_email_1`) appears in the queue 
with `status: "scheduled"` and `send_at` within the next 5 minutes.

### Step 4 — Confirm delivery

Check the email delivery log 10 minutes after triggering:

```
GET /internal/email/delivery-log?user_id={user_id}&limit=1
```

`status` should be `"delivered"`. If `"bounced"`, check the user's email 
address for typos and update via the account settings endpoint before 
re-triggering.

---

## Email sequence contents

| # | Template ID | Subject | Sent at |
|---|-------------|---------|---------|
| 1 | `welcome_email_1` | Welcome to Acme — let's get you set up | Immediately |
| 2 | `welcome_email_2` | Your first integration in 5 minutes | Day 2 |
| 3 | `welcome_email_3` | How teams use Acme to ship faster | Day 4 |
| 4 | `welcome_email_4` | You have unused features waiting | Day 7 |
| 5 | `welcome_email_5` | Need help? Here's everything available | Day 10 |

---

## Idempotency guarantee

The `/sequences/trigger` endpoint deduplicates by `(user_id, sequence)`. 
Triggering the same sequence twice within 24 hours is a no-op — the second 
call returns 200 with `{ "action": "skipped", "reason": "already_running" }`.

---

## Rollback

There is no rollback for emails already delivered. To cancel a sequence 
before delivery:

```
DELETE /internal/email/queue?user_id={user_id}&sequence=welcome_onboarding_v3
```

This cancels all pending (not yet sent) emails in the sequence.

---

## Related

- Runbook: Resend Individual Email
- Runbook: Update User Email Address
- Policy: Email Frequency Limits (max 2 marketing emails per week per user)
