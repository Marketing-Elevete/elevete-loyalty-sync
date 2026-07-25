#!/usr/bin/env python3
"""
Elevete Fam — loyalty catalogue sync (cloud / stateless).

Runs on company CI (GitHub Actions) every hour. Fetches the live LoyaltyLion program config and
writes it into the Shopify page metafield the rewards page reads. That's the ONE piece of the
loyalty ecosystem that isn't already vendor-native — everything else (earning, tiers, redemptions,
LoyaltyLion→Klaviyo, Klaviyo flows, and the page's live per-member render) runs on the vendors'
own servers and needs nothing here.

Design: STATELESS and IDEMPOTENT. No snapshot, no diff, no theme push. It just publishes the
current config every run, so it's safe to run any number of times and survives with no local
state. (The richer diff/build/push flow lives in sync_config.py for a developer machine; this is
the trimmed cloud path.)

Keys come from ENV, never files — so it runs on company infrastructure with no dependency on any
individual's laptop or home folder:
    LOYALTYLION_HEADLESS_KEY   — LoyaltyLion Manage → API keys (needs read_customers; keep server-side)
    SHOPIFY_ADMIN_TOKEN        — Shopify custom app token with write_content

Must run from the folder containing build_section.py + flavour_images.json (the repo root).
See CLOUD-SYNC-SETUP.md.
"""
import json, os, sys
import sync_config as sc


def main():
    missing = [v for v in ('LOYALTYLION_HEADLESS_KEY', 'SHOPIFY_ADMIN_TOKEN')
               if not (os.environ.get(v) or '').strip()]
    if missing:
        print('ERROR: missing env secret(s): %s' % ', '.join(missing))
        return 2
    try:
        cfg = sc.fetch()
    except Exception as e:
        print('ERROR: LoyaltyLion config fetch failed: %s' % str(e)[:200])
        return 2
    # build_section (imported by render_ready) reads this path — write it before rendering.
    json.dump(cfg, open(sc.LIVE_CONFIG, 'w'))
    try:
        ok = sc.publish_metafield(sc.render_ready(cfg))
    except Exception as e:
        print('ERROR: render/publish failed: %s' % str(e)[:200])
        return 2
    print('catalogue metafield: %s' % ('published OK' if ok else 'PUBLISH FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
