# Runbook: Reset Trial Account

**Owner:** Customer Success Engineering  
**Last reviewed:** 2026-06-01  
**Risk level:** Low — fully reversible  
**Automation status:** Safe to automate (no approval required)

---

## Purpose

Reset a customer's trial period back to 14 days remaining, clear any usage 
limits they have hit, and restore full feature access. This is the single 
most common CS operation and is entirely reversible at any time.

---

## Steps

### Step 1 — Verify the account exists and is in trial status

```
GET /internal/accounts/{account_id}
```

Confirm:
- `account.plan == "trial"`
- `account.status == "active"` or `"trial_expired"`

If the account is on a paid plan, stop here — this runbook does not apply.

### Step 2 — Reset trial expiry date

```
POST /internal/accounts/{account_id}/reset-trial
Body: { "extend_days": 14, "reason": "<ticket_id>" }
```

This sets `trial_expires_at = now() + 14 days`. The operation is idempotent 
— running it twice has the same effect as running it once.

### Step 3 — Clear usage counters

```
POST /internal/accounts/{account_id}/clear-usage
Body: { "counters": ["api_calls", "seats", "storage_gb"] }
```

Resets all rate-limit and quota counters to zero for the current billing 
window. Does not affect historical usage logs.

### Step 4 — Re-enable any locked features

If the account has feature flags that were auto-disabled after trial expiry, 
re-enable them:

```
PATCH /internal/accounts/{account_id}/features
Body: { "trial_features": "enabled" }
```

### Step 5 — Send confirmation email

Trigger the "trial reset" email template to the account owner:

```
POST /internal/notifications/send
Body: {
  "template": "trial_reset_confirmation",
  "account_id": "{account_id}",
  "variables": { "days_remaining": 14 }
}
```

---

## Verification

After all steps, confirm in the admin dashboard:
- Trial expiry shows 14 days from today
- Usage meters show 0
- Account owner receives confirmation email within 2 minutes

---

## Rollback

This operation is fully reversible. To undo:
- Set `trial_expires_at` to any previous value via the same PATCH endpoint
- Usage counters cannot be restored (they were zeroed), but this is acceptable

---

## Related

- Runbook: Extend Trial (adds days without resetting)
- Policy: Trial Extension Approval (for extensions > 30 days)
- Runbook: Upgrade Trial to Paid Plan
