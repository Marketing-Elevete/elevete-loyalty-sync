# Elevete Fam — loyalty catalogue sync (cloud setup & handover)

**Purpose.** Keep the rewards page's **reward list, costs, tier names, and earn rates** in step with
LoyaltyLion, automatically, **without depending on any individual's computer.** This is the *only*
part of the loyalty ecosystem that isn't already vendor-native — so making it company-owned makes
the whole thing survive staff turnover.

**Anyone maintaining this needs no prior context and does not need Claude.** Follow this file.

---

## What runs where (so you know what this does and doesn't cover)

| Part of the program | Where it runs | Needs this job? |
|---|---|---|
| Earn Crumbs on purchase, tier assignment, redemptions | Shopify ↔ LoyaltyLion (vendor servers) | No |
| Tier/points synced onto Klaviyo profiles | LoyaltyLion → Klaviyo (vendor) | No |
| Lifecycle emails/flows | Klaviyo (vendor) | No |
| **Everything a logged-in member sees change** (balance, tier, progress, lock states, expiry) | Read **live** from the LoyaltyLion SDK on every page load | No |
| **The reward catalogue shown on the page** (which rewards exist, costs, tier names, earn rates) | Baked into a Shopify **page metafield** | **YES — this job keeps it fresh** |

If this job stops, the page does **not** break: it keeps showing the last-synced catalogue and all
per-member data stays live. It just won't pick up a *new* catalogue change (e.g. a re-priced reward)
until it runs again. Catalogue changes are rare, so a missed hour is harmless.

Why it can't be fully client-side: LoyaltyLion's `/configuration` endpoint requires the
`read_customers` scope (verified 25 Jul 2026), so any key that can read the catalogue can also read
customer PII — such a key must never go in a browser. Hence a server-side job.

---

## One-time setup (≈10 minutes)

**1. Create a PRIVATE repo under the COMPANY GitHub org** (not a personal account — that's the whole
point). Put these files at the repo root:

```
build_section.py
sync_config.py
cloud_sync.py
flavour_images.json
.github/workflows/loyalty-sync.yml
```

**2. Add two repository secrets** — repo **Settings → Secrets and variables → Actions → New repository secret**:

| Secret name | Value | Where it comes from |
|---|---|---|
| `LOYALTYLION_HEADLESS_KEY` | the LoyaltyLion API key | LoyaltyLion → **Manage → API keys** (needs `read_customers`; keep it server-side only) |
| `SHOPIFY_ADMIN_TOKEN` | the Shopify custom-app token | Shopify custom app with **`write_content`** scope |

**3. Enable Actions** (Settings → Actions → allow), then open the **Actions** tab → *Elevete Fam — loyalty catalogue sync* → **Run workflow** to fire it once. A green run ending in
`catalogue metafield: published OK` means it works. After that it runs hourly on its own.

That's it. No servers, no laptop, no Claude.

---

## Verify it worked
- The Actions run log ends with `catalogue metafield: published OK`.
- Or: change a reward cost in LoyaltyLion, run the workflow manually, reload `/pages/rewards` in a
  fresh browser tab — the new cost shows.

## Maintenance
- **Key rotation** is the only thing that will ever break this. When either key is rotated,
  update the matching repo **secret**. Nothing else changes.
- **Don't move/rename** the five files or the metafield namespace (`sweet_club` / key `catalogue`).
- The job is idempotent — safe to re-run any time. There is no state to corrupt.

## What this job deliberately does NOT do
- No theme/code deploy (it only writes a data metafield).
- No per-member data (that's live via the SDK, never synced).
- No writes to LoyaltyLion or customers (read-only from LoyaltyLion; only writes the Shopify metafield).

---

## Ownership checklist for true independence
- [ ] Repo lives in the **company GitHub org**, not a personal account
- [ ] `LOYALTYLION_HEADLESS_KEY` is on the **company** LoyaltyLion account
- [ ] `SHOPIFY_ADMIN_TOKEN` is from a **company-owned** Shopify custom app
- [ ] At least two staff have admin on the repo + both vendor accounts

The same pattern (move it into the company GitHub org / cloud, keys as secrets) is how the other
laptop-based automations — Meta day-parting, growth tracker, data refresh — should be lifted off any
one person's machine so they, too, survive turnover.
