# Security: what we hold, what we outsource, what we must do ourselves

Same layered format as the guide. Level 0 is the principle. Level 4 is a checklist.

---

## Level 0: the principle

You are not a bank, so don't build a vault. You are a shop that takes payments: use the bank's vault and keep only the receipts. For manuscripts, you are a law firm holding client documents: the realistic risk is not a hacker cracking encryption, it is the wrong logged-in person seeing the wrong file.

Two rules fall out of that:

1. **Hold as little as possible.** Every piece of data you don't store is a breach that can't happen.
2. **Outsource anything that has a compliance regime attached** (card details, bank accounts, passwords, tax IDs). Companies exist whose whole job is bearing that risk, and they are cheaper than a single incident.

---

## Level 1: who attacks this product, and why

Security without a threat model is just anxiety. For a review marketplace the realistic attackers are:

| Attacker | Wants | Realistic route |
|---|---|---|
| **Competing researcher** | to read an unpublished manuscript (scooping) | sign up as a reviewer, guess or manipulate URLs to see manuscripts they weren't assigned |
| **Author** | to learn who reviewed them, or to influence the choice | metadata leaks, timing leaks, social engineering an editor |
| **Reviewer wanting money without work** | honoraria | submit junk, collude with an editor who rubber-stamps, fake multiple accounts |
| **Fraudster** | reviewers' payouts | take over a reviewer account and change the payout destination |
| **Opportunistic bot** | anything | credential stuffing, unpatched dependencies, exposed admin panels |

Notice that only the last one is a "hacker". The rest are ordinary users of the platform behaving badly. That shapes everything below: **authorisation logic** (who may see what) matters more than cryptography.

---

## Level 2: what we would have to store, by how dangerous it is

Think of data in tiers. The tier decides whether you store it at all.

### Tier 1: radioactive. Never store. Outsource.
- Card numbers, bank account details, sort codes, IBANs
- Passwords
- Tax identifiers (NI numbers, SSNs, VAT IDs for reviewers)
- Government ID documents (for payout KYC)

If any of this touches your database you inherit PCI DSS, KYC/AML obligations, and a very expensive breach. None of it is needed: Stripe holds the bank details, ORCID holds the password.

### Tier 2: confidential. The crown jewels of this product.
- **Unpublished manuscripts.** A leak is career-damaging for the author and reputation-ending for you. A publisher will ask exactly how you protect these before signing anything.
- **Who reviewed what.** In single- or double-blind review, the reviewer's identity per manuscript is a secret you are contractually holding.
- Review content and recommendations
- Conflict-of-interest declarations
- Editor ratings of reviewers

### Tier 3: personal data. Protect, and comply with GDPR/UK GDPR.
- Name, email, ORCID iD, affiliation
- Reviewer preferences, blackout dates, charity choice
- Ledger balances and payout history (financial data about a person)
- Invitation and behaviour history (the raw stats behind reliability)

### Tier 4: public. Store freely.
- Publication lists, co-authorship graph (all from OpenAlex, already public)
- Journal names, honorarium rates if the publisher makes them public

**What the prototype already gets right:** the ledger records reviewer *ids*, not bank details. `withdraw` moves money to an `external` account and stops. That is exactly the seam where a payment provider plugs in.

---

## Level 3: off-the-shelf solutions for the risky parts

### Identity and login: never store a password
- **ORCID OAuth** for reviewers. You already require ORCID for identity; use it for login too. You store the ORCID iD and a token, never a password. Bonus: a fake reviewer needs a real ORCID with real publications, which raises the cost of fraud enormously.
- **An auth platform** (Auth0, Clerk, WorkOS, or Supabase Auth) to handle sessions, 2FA, magic links for editors, and **SAML/SSO for publishers**, who will insist their staff log in with the corporate identity. Building SSO yourself is months of work and a well-known source of bugs.

### Money: Stripe Connect (or equivalent)
This is the single biggest risk-transfer available to you.
- **Stripe Connect** is built for marketplaces: publishers pay you, you pay reviewers, Stripe holds every bank detail, runs KYC on reviewers, handles currency conversion, and produces tax forms (1099 in the US, DAC7 reporting in the EU). You never see a bank account.
- Alternatives: **Adyen for Platforms**, **Wise Platform**, **PayPal Payouts**. Stripe has the best marketplace tooling; Wise has the best international payout fees.
- **Your ledger stays.** It is your internal source of truth and reconciles against Stripe daily. Stripe is the rails; the ledger is the accounts book. The prototype's `withdraw` becomes: post the ledger entry only when Stripe's webhook confirms the transfer, and verify the webhook signature.

### Manuscript files: object storage with expiring links
- **S3 / Google Cloud Storage / Cloudflare R2**, private bucket, server-side encryption on by default, versioning off (you want deletion to mean deletion).
- Access via **signed URLs that expire in minutes**, generated only after your authorisation check passes. Nobody ever gets a permanent link.
- Optional: render to a **watermarked, view-only PDF** per reviewer (services: PSPDFKit, Adobe PDF Embed). Makes a leaked copy traceable and deters casual scooping.
- Never attach a manuscript to an email. Email a link that requires login.

### Secrets, hosting, patching
- **Secrets manager** (AWS Secrets Manager, GCP Secret Manager, Doppler). API keys never live in code or `.env` files in the repo.
- **Managed hosting** (Vercel, Fly.io, Render, or a managed Kubernetes) so OS patching is someone else's job. **Managed Postgres** (Neon, Supabase, RDS) gives you encryption at rest, backups, and point-in-time recovery for free.
- **Cloudflare** in front of everything: TLS, WAF, bot filtering, DDoS absorption, rate limiting.
- **Dependabot or Snyk** for dependency vulnerabilities. Most real-world breaches of small products come through an unpatched library, not clever attacks.

### Compliance paperwork
- **Vanta or Drata** to get to **SOC 2** when a large publisher's procurement asks for it. They will. Budget for it in year two, not year one.
- **Data Processing Agreement** template: you are a *processor* for manuscripts (the publisher is the controller) and a *controller* for reviewer profiles. A lawyer drafts this once.

---

## Level 4: what you cannot outsource

These are yours. They are product logic, and no vendor knows your product.

### 1. Authorisation: who may see which manuscript
The number one bug class in marketplaces is **IDOR** (insecure direct object reference): change `/manuscripts/m3` to `/manuscripts/m4` in the URL and see someone else's paper. Defence is boring and essential:
- Every request that touches a manuscript, review, or invitation checks: *is this user the editor of this journal, or a reviewer with an ACCEPTED invitation for this exact manuscript?* Not "is the user logged in". The specific relationship.
- Put that check in **one function** that every code path calls, and write tests that try to cross the line (reviewer A requests reviewer B's manuscript, expects 403).
- Postgres **row-level security** can enforce it at the database layer as a second net.

### 2. Blind-review leaks through side channels
Encryption doesn't help when the leak is in the metadata. Places reviewer identity escapes:
- **File properties** on an uploaded review (author name in the PDF metadata). Strip on upload.
- **Ledger memos and statements.** A publisher's statement must say "review #3 for manuscript m3 paid", never the reviewer's name. The prototype's memos use invitation ids, which is right; keep it that way when building publisher-facing exports.
- **Timing.** "Reviewer accepted at 14:02" combined with an email notification at 14:02 to a known person. Batch or jitter notifications.
- **Error messages and logs.** "Reviewer p214 cannot access manuscript m9" in a log an editor can see.

### 3. Payout fraud, the product-specific kind
- **Account takeover to redirect payouts** is the classic marketplace attack. Changing a payout destination should require: re-authentication, email confirmation to the *old* address, and a 24-48 hour cooling-off before the next withdrawal. Stripe Connect handles the bank-detail change itself, but the cooling-off is your rule.
- **Collusion** (editor repeatedly approving the same reviewer's junk). Detect with simple stats: same editor-reviewer pair approved N times in a month, reviews under a minimum length, approval within minutes of submission. Flag for human review; don't auto-block.
- **Sock puppets.** ORCID with a minimum publication count blocks most of it. Add: one payout destination per person (Stripe dedupes on KYC identity).

### 4. Ledger integrity in a real database
The prototype's four rules become database facts:
- The ledger table is **append-only**: the application's database role has INSERT and SELECT only, no UPDATE or DELETE. Corrections are reversing entries.
- A **check constraint or trigger** rejects any transaction whose legs don't sum to zero.
- The idempotency key is a **unique index**.
- A **nightly reconciliation job** compares ledger balances with Stripe's balance and alerts on any difference. Silent drift is how money goes missing.

### 5. Data minimisation and retention
- Delete manuscript files N days after the editorial decision (30 is typical). Keep the *record* that a review happened; drop the *content*.
- Keep reviewer behaviour stats, drop raw invitation history after a year.
- Provide export and delete for reviewers (GDPR rights). This is easier to build on day one than retrofit.
- Host EU/UK data in EU/UK regions. Publishers will ask.

### 6. Audit log
Every access to a manuscript file, every payout, every change of payout destination, every admin action: who, what, when, from where. Append-only, separate from application logs, retained a year. When a publisher asks "who opened this manuscript?", this is the only acceptable answer.

### 7. Reviewer confidentiality agreement
A click-through per invitation ("I will not share or use this manuscript") is a legal control, not a technical one, but it is what makes the watermark and audit log enforceable.

---

## The stack, in one table

| Concern | Do it yourself? | Use |
|---|---|---|
| Passwords | No | ORCID OAuth + auth platform (Clerk/Auth0/WorkOS) |
| Publisher SSO | No | WorkOS or Auth0 (SAML) |
| Bank details, KYC, tax forms, payouts | No | Stripe Connect (or Adyen, Wise) |
| Card payments from publishers | No | Stripe |
| File encryption at rest | No | S3/GCS/R2 default encryption |
| Database encryption, backups | No | Managed Postgres |
| TLS, DDoS, WAF, rate limiting | No | Cloudflare |
| Secrets | No | Cloud secrets manager |
| OS patching | No | Managed hosting |
| Dependency vulnerabilities | No | Dependabot/Snyk |
| SOC 2 evidence | No | Vanta/Drata |
| **Who may see which manuscript** | **Yes** | one authorisation function + tests + RLS |
| **Blind-review side channels** | **Yes** | metadata stripping, anonymised statements, jittered notifications |
| **Ledger append-only + reconciliation** | **Yes** | DB grants, constraints, nightly job |
| **Payout-change cooling-off** | **Yes** | product rule |
| **Collusion detection** | **Yes** | simple stats, human review |
| **Retention and deletion** | **Yes** | scheduled job |
| **Audit log** | **Yes** | append-only table |

---

## What this means for the prototype

Nothing in the current code needs to change to support this. Three things to add before any real data touches it:

1. An `authz.py` with one function, `can_access(user, resource) -> bool`, and a test file that tries every wrong combination.
2. An `audit.py` that appends `(who, action, resource, at)` and is called by the same paths that call `can_access`.
3. In `payments/flows.py`, split `withdraw` into `request_withdrawal` (creates a pending record) and `confirm_withdrawal` (posts the ledger entry, called from the payment provider's webhook after signature verification).

*Tags: reviewmatch, security, architecture, cit_rep*
