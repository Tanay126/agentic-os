# Policy: Employee Account Termination

**Owner:** IT Security & HR  
**Classification:** Confidential — HR use only  
**Last reviewed:** 2026-03-20  
**Applies to:** All full-time employees, contractors, and vendors

---

## Overview

Employee account termination is a high-stakes, **irreversible** process. 
Once access is revoked and accounts are deprovisioned, recovery requires 
a formal re-hiring workflow and takes a minimum of 3 business days.

**This process must never be automated without explicit HR and Legal 
sign-off on each individual case.** Errors have legal, compliance, and 
reputational consequences.

---

## Required approvals before any action

Before initiating termination, you MUST have:

1. **Signed termination notice** from the employee's direct manager, 
   countersigned by HR Business Partner
2. **Legal clearance** — Legal must confirm there are no pending 
   litigation holds (litigation hold = all data must be preserved, not deleted)
3. **IT Security ticket** opened in Jira under project `ITSec-Offboarding` 
   with tag `account-termination`, approved by the CISO or delegate
4. For contractors: **additional sign-off from the vendor's account manager** 
   confirming contract termination

Do NOT proceed with any of the steps below until all 4 approvals are in Jira.

---

## Termination steps (IT Security only)

### Step 1 — Revoke SSO and IdP access

Disable the employee's account in Okta:
- Set account status to `Suspended` (not Deleted — preserves audit trail)
- This immediately terminates all active SSO sessions
- Confirm in the Okta audit log that all sessions show `terminated`

**Do not delete the Okta account for 90 days** — required for audit trail 
and potential litigation hold compliance.

### Step 2 — Revoke production system access

In order, revoke access to:
1. GitHub organization (remove from all teams; do not delete their commits)
2. AWS IAM (disable all access keys and console login)
3. GCP IAM (revoke all project memberships)
4. Datadog, PagerDuty, Sentry (deactivate account)
5. Customer data systems (Salesforce, Zendesk, admin portal)

Each revocation must be logged in the ITSec Jira ticket with timestamp.

### Step 3 — Rotate shared secrets the employee had access to

Check the Vault audit log for all secrets accessed by this employee in the 
past 90 days. Rotate any shared API keys, database passwords, or service 
tokens they could have cached locally.

This step is mandatory — it cannot be skipped even if the termination is 
amicable.

### Step 4 — Transfer ownership of business-critical assets

Before deprovisioning:
- Google Workspace: transfer Drive files to manager
- GitHub: reassign open PRs to team lead
- Notion: transfer pages to department head
- PagerDuty on-call rotations: manually update schedule

Failure to transfer assets may cause production incidents.

### Step 5 — Archive and preserve data (90-day hold)

Do NOT delete any email, Slack, or document data for 90 days post-termination. 
Archive the employee's:
- Google Workspace account data to the offboarding GCS bucket
- Slack message history (export via Slack admin)
- GitHub activity (already preserved by Git history)

If Legal has issued a litigation hold, the retention period extends 
indefinitely until Legal explicitly releases it.

### Step 6 — Final audit and sign-off

Submit a completion report to HR with:
- Timestamp of each access revocation
- List of secrets rotated
- Confirmation that data was archived
- Any anomalies or exceptions encountered

HR countersigns and closes the Jira ticket. Completion SLA: 4 hours from 
start of Step 1 (for involuntary terminations), 24 hours (for voluntary).

---

## Involuntary termination (immediate)

For involuntary terminations (layoffs, misconduct, security incidents), 
Step 1 (SSO revocation) must happen **simultaneously** with the employee 
notification call — IT Security holds on the phone until HR gives the go-ahead.

---

## What never to do

- Do not delete the Okta user account before 90 days
- Do not skip secret rotation, even for amicable departures
- Do not terminate access before receiving all 4 approvals
- Do not discuss the termination details in public Slack channels
