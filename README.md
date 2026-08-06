# elevete-loyalty-sync

Keeps the Elevete Fam rewards page in sync with LoyaltyLion.

## What runs automatically

A GitHub Action runs `cloud_sync.py` **every 5 minutes**. It reads the live LoyaltyLion
configuration and publishes it to the Shopify metafield
`page.metafields.sweet_club.catalogue`.

The rewards page section reads that metafield at render time. So **anything changed in
LoyaltyLion reaches the live page within 5 minutes, with no code change and no deploy**:

- new or removed rewards, cake slices and vouchers
- renamed rules
- tier names, thresholds and earn rates
- the referral offer

Member data — points balance, tier, history, claimed rewards, challenge progress — does not go
through this repo at all. It comes from the LoyaltyLion SDK in the customer's browser and
updates in real time.

## ⚠️ This repo no longer generates the page

`build_section.py` used to write `sections/rewards-club.liquid`. **It doesn't any more.**

That section is now hand-maintained in the Shopify theme repo. It carries the member account
hub, membership card, flavour passport, milestones, the challenge tracker and a set of
accessibility fixes, none of which exist in this generator. Its JavaScript also moved to
`assets/rewards-club.js` because the inline version breached Shopify's **256KB section limit**.

Running the generator against the live section would delete all of that and re-break the size
limit. The write is now guarded and will refuse unless you explicitly opt in — and even then
the output is not deployed.

Full workflow, including where each kind of change belongs: `REWARDS-PAGE.md` in the theme repo.

## Files

| File | Purpose |
|---|---|
| `cloud_sync.py` | Cron entry point. Fetch LoyaltyLion config → publish the Shopify metafield. |
| `sync_config.py` | Fetch and metafield-publish helpers. Reads keys from env, falls back to local files. |
| `build_section.py` | **Legacy.** Still imported for `render_ready()`. Does not generate the live section. |
| `.github/workflows/` | The 5-minute schedule. |
| `CLOUD-SYNC-SETUP.md` | One-time setup, secrets, key rotation, ownership. |

## Secrets

Two repository secrets: `LOYALTYLION_HEADLESS_KEY` and `SHOPIFY_ADMIN_TOKEN`.
Rotation steps are in `CLOUD-SYNC-SETUP.md`.
