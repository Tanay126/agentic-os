# Policy: Customer Refund Policy

**Owner:** Finance & Revenue Operations  
**Effective date:** 2026-01-15  
**Last updated:** 2026-04-10  
**Applies to:** All paid subscription plans (monthly and annual)

---

## Summary

This policy governs how to refund a customer subscription payment. Customer 
refunds can be processed by CS agents for amounts up to $500 without additional 
approval. Refunding a customer requires manager approval when the refund amount 
exceeds $500 or falls outside the standard refund window. Some refund cases 
require human judgment (edge cases, disputes, custom contracts) and cannot be 
fully automated.

---

## Standard refund rules

### Monthly plans

- Full refund available within **7 days** of the charge date, no questions asked
- After 7 days: prorated refund for unused days, issued as account credit only
- No cash refunds after 30 days from the charge date

### Annual plans

- Full refund within **30 days** of the initial purchase
- After 30 days: prorated refund for unused months, issued as account credit
- No cash refunds after 90 days from annual plan purchase

---

## Automatic approvals (no manager required)

Customer Success agents may approve refunds without escalation when ALL of 
the following are true:

1. Refund amount is **$500 or less**
2. The customer is within the standard refund window (above)
3. The customer has not requested more than 2 refunds in the past 12 months
4. The account has no active fraud flags

Use the CS admin portal → Billing → Issue Refund to process.

---

## Manager approval required

**Manager approval is required for refunds greater than $500.**

Also escalate to a manager when any of the following apply:

- Customer has requested 3 or more refunds in the past 12 months
- Account has an active fraud or chargeback investigation
- Customer is threatening legal action or a public complaint (Trustpilot, 
  App Store review)
- Refund is requested more than 90 days after the charge
- Request involves a custom enterprise contract — loop in Revenue Operations

To escalate: open a ticket in Linear under `CS-Escalations` with tag 
`refund-approval-needed`. Response SLA is 4 business hours.

---

## Edge cases and exceptions

### "I didn't use the product" claims

Usage data is the source of truth. If the customer logged in fewer than 
3 times and made fewer than 10 API calls during the billing period, treat 
the request as a standard refund regardless of timing. Pull usage from the 
admin dashboard before deciding.

### Duplicate charges

Always refund duplicate charges in full, immediately, regardless of amount. 
No approval required. Mark the duplicate transaction as `void` in Stripe.

### Failed feature claims

If a customer claims they were charged for a feature that was broken or 
unavailable during their billing period, loop in Engineering via the 
`#customer-escalations` Slack channel to verify the incident before issuing 
any refund. Do not promise a refund before engineering confirms the outage.

### Annual-to-monthly downgrades

When a customer downgrades from annual to monthly mid-cycle, calculate 
the prorated refund using: `(months_remaining / 12) × annual_price × 0.85`. 
The 0.85 factor accounts for the annual discount they received. Manager 
approval required if the resulting refund exceeds $500.

---

## Processing time

- Credit card refunds: 5–10 business days to appear on statement
- Account credits: applied immediately, visible in billing portal
- ACH/wire refunds: 3–5 business days

---

## Audit trail

Every refund must include a reason code in the CS ticket. Valid codes:

| Code | Meaning |
|------|---------|
| `within-window` | Standard refund within policy window |
| `duplicate-charge` | Billing error / duplicate |
| `feature-unavailable` | Product was down or feature didn't work |
| `customer-dissatisfied` | Customer unhappy, goodwill refund |
| `manager-exception` | Approved outside standard policy |
