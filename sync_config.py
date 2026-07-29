#!/usr/bin/env python3
"""
Keep the Sweet Club page in step with LoyaltyLion — WITHOUT putting a key in the browser.

WHY THIS EXISTS
    Rewards, rules, tier benefits, earn rates and thresholds are baked into the section at build
    time. Change any of them in the LoyaltyLion admin and the storefront keeps showing the old
    values, with no error — it just quietly misinforms. GO-LIVE STEP 4c asks a human to remember
    to rebuild. Humans don't.

WHY NOT JUST FETCH IT IN THE BROWSER
    Verified 23 Jul 2026: the "headless" key is NOT storefront-safe. It returns 200 on the ADMIN
    v2 API and will hand back email + birthday + points for every customer. A garbage token gets
    401, so that access is real, not an unauthenticated endpoint. It must never reach page source.
    True in-browser real-time needs a publishable/storefront-scoped token from LoyaltyLion —
    ask Sammy. Until then, this script is the safe equivalent: the key stays on this machine.

WHAT IT DOES
    fetch config -> compare against the last snapshot -> if anything a customer can SEE changed,
    rebuild the section and report exactly what moved. Optionally pushes.

USAGE
    python3 sync_config.py                 # check + report only (safe, default)
    python3 sync_config.py --build         # also rebuild the section if changed
    python3 sync_config.py --build --push  # ...and push to staging + live
    python3 sync_config.py --force         # rebuild even if nothing changed

EXIT CODES
    0 no change   1 changed   2 error (fetch failed / key missing)
"""
import json, os, subprocess, sys, urllib.request, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.expanduser('~/.loyaltylion_headless_key')
CONFIG_URL = 'https://api.loyaltylion.com/headless/2025-06/61360/configuration'
LIVE_CONFIG = '/tmp/ll_config.json'
SNAPSHOT = os.path.join(HERE, '.config-snapshot.json')
LOG = os.path.join(HERE, 'sync-log.md')
LIVE_THEME, STAGING_THEME = '187707425064', '187889320232'


def fetch():
    """Via curl, not urllib: the system Python on macOS ships without a CA bundle, so urllib
    fails with CERTIFICATE_VERIFY_FAILED on a clean machine. curl uses the OS trust store."""
    # Key from env first (cloud/GitHub Actions), then the local file (dev machine). Lets the
    # SAME code run on a laptop and on company CI without edits.
    key = (os.environ.get('LOYALTYLION_HEADLESS_KEY') or '').strip()
    if not key:
        if not os.path.exists(KEY_FILE):
            sys.exit('ERROR: no LOYALTYLION_HEADLESS_KEY env and %s missing' % KEY_FILE)
        key = open(KEY_FILE).read().strip()
    p = subprocess.run(['curl', '-sS', '--fail-with-body', '-m', '30',
                        '-H', 'Authorization: Bearer ' + key,
                        '-H', 'X-LoyaltyLion-Channel: web', CONFIG_URL],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or 'curl failed').strip()[:300])
    return json.loads(p.stdout)


def visible(cfg):
    """Reduce the config to ONLY what a customer can see on the page.

    Anything outside this projection (internal ids, timestamps, unrelated settings) must not be
    able to trigger a rebuild — otherwise the job churns on noise and everyone starts ignoring it.
    """
    def fv(x):
        vs = [v for v in (x.get('variants') or []) if v.get('enabled')]
        return vs[0] if vs else ((x.get('variants') or [{}])[0])

    out = {'rewards': {}, 'rules': {}, 'tiers': {}, 'referee': {}}

    for r in cfg.get('rewards', []):
        v = fv(r)
        out['rewards'][str(r.get('id'))] = {
            'title': (v.get('title') or '').strip(),
            'points': (v.get('cost') or {}).get('points'),
            'kind': r.get('kind'),
            'min_spend': ((r.get('properties') or {}).get('minimum_spend') or {}).get('amount'),
        }

    for r in cfg.get('rules', []):
        v = fv(r)
        out['rules'][str(r.get('id'))] = {
            'kind': r.get('kind'),
            'title': (v.get('title') or '').strip(),
            'text': (v.get('result_short_text') or '').strip(),
            # Keyed BY TIER, not a list: a list diff dumps the whole array and you can't see which
            # tier moved. Keyed, a changed earn rate reads as `rules.<id>.tiers.28162.points: 5 -> 6`.
            'tiers': {str(x.get('tier_id')): {
                'on': x.get('enabled'),
                'points': (x.get('result') or {}).get('points'),
                'per_rm': (x.get('result') or {}).get('per_currency_unit'),
                'short': (x.get('result_short_text') or '').strip(),
            } for x in (r.get('variants') or [])},
            'limit': r.get('limit'),
        }

    tc = cfg.get('tier_configuration') or {}
    for t in tc.get('tiers', []):
        out['tiers'][str(t.get('id'))] = {
            'name': t.get('name'), 'position': t.get('position'),
            'lower': (t.get('lower_bound') or {}).get('amount'),
            'upper': (t.get('upper_bound') or {}).get('amount'),
            'benefits': sorted(t.get('benefit_ids') or []),
        }
    out['tiers']['_mode'] = tc.get('boundary_mode')

    ri = cfg.get('referee_incentive') or {}
    out['referee'] = {'min': (ri.get('minimum_spend') or {}).get('amount'),
                      'discount': (ri.get('discount') or {}).get('amount'),
                      'kind': ri.get('kind')}
    return out


def diff(old, new, path=''):
    """Human-readable list of what a customer would notice changing."""
    changes = []
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new)):
            p = '%s.%s' % (path, k) if path else k
            if k not in old:
                changes.append('+ ADDED   %s = %s' % (p, json.dumps(new[k])[:110]))
            elif k not in new:
                changes.append('- REMOVED %s (was %s)' % (p, json.dumps(old[k])[:110]))
            else:
                changes += diff(old[k], new[k], p)
    elif old != new:
        changes.append('~ CHANGED %s: %s -> %s' % (path, json.dumps(old)[:70], json.dumps(new)[:70]))
    return changes


def render_ready(cfg):
    """Build exactly what Liquid needs to draw the reward grids — no logic left for the theme.

    Image matching, tier labelling and title cleanup all happen HERE, server-side, so the section
    stays a dumb renderer. Reuses build_section.py's own helpers so the live path and the baked
    fallback can never disagree about how a reward is presented.
    """
    sys.path.insert(0, HERE)
    import importlib.util
    spec = importlib.util.spec_from_file_location('bs', os.path.join(HERE, 'build_section.py'))
    bs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bs)          # build_section reads /tmp/ll_config.json, already fresh
    def fv(x):
        vs = [v for v in (x.get('variants') or []) if v.get('enabled')]
        return vs[0] if vs else ((x.get('variants') or [{}])[0])

    # TIERS drive almost every number the member sees — the unlock lines, the ringgit conversion on
    # locked rewards, the simulator, the "what it's worth" line and the tracker. Getting them from
    # the config instead of a hardcoded array is the single highest-leverage thing here: change an
    # earn rate in LoyaltyLion and all of those follow at once.
    purchase = next((r for r in cfg.get('rules', []) if r.get('kind') == 'purchase'), None)
    rate_by_tier = {}
    for v in ((purchase or {}).get('variants') or []):
        res = v.get('result') or {}
        if v.get('enabled') and res.get('points'):
            rate_by_tier[v.get('tier_id')] = res['points']

    tiers = []
    for t in sorted((cfg.get('tier_configuration') or {}).get('tiers', []),
                    key=lambda x: x.get('position') or 0):
        tiers.append({
            'id': t.get('id'), 'name': t.get('name'),
            'min': (t.get('lower_bound') or {}).get('amount') or 0,
            'max': (t.get('upper_bound') or {}).get('amount'),
            'rate': rate_by_tier.get(t.get('id')) or 0,
        })

    # Earn tiles: the ways to earn that don't already have their own surface on the page.
    earn = [{'kind': r['kind'], 'icon': r['icon'], 'title': r['title'], 'text': r['text'],
             # id lets the rewards page attach data-rid → the tile opens LoyaltyLion's action
             # modal (openRuleActionModal) and credits the follow/review. Auto rules (join, birthday)
             # carry an id too but the page gates them on data-auto so they never become claim buttons.
             'id': r.get('id'),
             'auto': 1 if r['kind'] in bs.AUTO_KINDS else 0} for r in bs.other_earn]
    ref = next((r for r in bs.rules if r['kind'] == 'referral'), None)

    return {
        'v': 2,
        'updated': datetime.datetime.now().isoformat(timespec='seconds'),
        'vouchers': [{'id': str(v['id']), 'amt': v['amt'], 'pts': v['pts']} for v in bs.vouchers],
        'slices': [{'id': str(s['id']), 'title': s['title'], 'pts': s['pts'],
                    'tier': s['tier'], 'img': s['img'] or ''} for s in bs.slices],
        'tiers': tiers,
        'earn': earn,
        'referral': {'icon': ref['icon'], 'title': ref['title'], 'text': ref['text']} if ref else None,
    }


def publish_metafield(payload):
    """Write the catalogue to BOTH pages: the hidden preview and the public rewards page, so the
    STEP 5 handle switch needs no extra step and can't land on an empty metafield."""
    token = (os.environ.get('SHOPIFY_ADMIN_TOKEN') or '').strip()
    if not token:
        tok_file = os.path.expanduser('~/.shopify_admin_token')
        if not os.path.exists(tok_file):
            print('  ! no SHOPIFY_ADMIN_TOKEN env and no token file — skipping metafield publish')
            return False
        token = open(tok_file).read().strip()
    fields = [{'ownerId': 'gid://shopify/Page/%s' % pid, 'namespace': 'sweet_club',
               'key': 'catalogue', 'type': 'json', 'value': json.dumps(payload)}
              for pid in ('162288632104', '158410932520')]
    q = ('mutation($m:[MetafieldsSetInput!]!){metafieldsSet(metafields:$m)'
         '{metafields{id} userErrors{field message}}}')
    body = json.dumps({'query': q, 'variables': {'m': fields}})
    p = subprocess.run(['curl', '-sS', '-m', '30', '-X', 'POST',
                        'https://elevete-patisserie.myshopify.com/admin/api/2024-10/graphql.json',
                        '-H', 'X-Shopify-Access-Token: ' + token,
                        '-H', 'Content-Type: application/json', '-d', body],
                       capture_output=True, text=True)
    try:
        r = json.loads(p.stdout)
        errs = (r.get('data', {}).get('metafieldsSet', {}) or {}).get('userErrors', [])
        wrote = len((r.get('data', {}).get('metafieldsSet', {}) or {}).get('metafields', []) or [])
    except Exception:
        print('  ! metafield publish failed: %s' % (p.stdout or p.stderr)[:200]); return False
    if errs or not wrote:
        print('  ! metafield publish rejected: %s' % json.dumps(errs)[:200]); return False
    print('  metafield published to %d page(s): %d vouchers, %d slices'
          % (wrote, len(payload['vouchers']), len(payload['slices'])))
    return True


def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def main():
    args = sys.argv[1:]
    do_build, do_push, force = '--build' in args, '--push' in args, '--force' in args

    try:
        cfg = fetch()
    except Exception as e:
        print('ERROR: could not fetch LoyaltyLion config: %s' % e)
        print('       (a 403 here usually means the programme is still offline)')
        return 2

    now = visible(cfg)
    was = json.load(open(SNAPSHOT)) if os.path.exists(SNAPSHOT) else None

    if was is None:
        print('No snapshot yet — recording the current config as the baseline.')
        json.dump(now, open(SNAPSHOT, 'w'), indent=1, sort_keys=True)
        json.dump(cfg, open(LIVE_CONFIG, 'w'))
        return 0

    changes = diff(was, now)
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    if not changes and not force:
        print('[%s] No customer-visible change. Page is in step.' % stamp)
        return 0

    # Publish FIRST. The metafield is what the storefront actually reads for the reward grids, so
    # this alone brings the page in step on the next load — even if the rebuild/push below is
    # skipped or fails. Rules, tier values and FAQ figures are still baked, so a --build is still
    # wanted when those move; the metafield just means rewards never wait for a deploy.
    json.dump(cfg, open(LIVE_CONFIG, 'w'))
    try:
        publish_metafield(render_ready(cfg))
    except Exception as e:
        print('  ! could not build/publish catalogue metafield: %s' % str(e)[:200])

    print('[%s] %d customer-visible change(s):\n' % (stamp, len(changes)))
    for c in changes:
        print('   ' + c)

    # The page quotes these numbers as promises, so a change here is not cosmetic.
    if not do_build:
        print('\nThe live page is now STALE. Re-run with --build (add --push to deploy).')
        return 1

    json.dump(cfg, open(LIVE_CONFIG, 'w'))
    rc, out = run('python3 build_section.py', cwd=HERE)
    if rc != 0:
        print('\nBUILD FAILED — nothing deployed, snapshot NOT advanced:\n' + out[-1500:])
        return 2
    print('\n' + out.strip().splitlines()[-2])

    if do_push:
        run('cp rewards-club.liquid themework/sections/rewards-club.liquid', cwd=HERE)
        tw = os.path.join(HERE, 'themework')
        for theme, extra in ((STAGING_THEME, ''), (LIVE_THEME, ' --allow-live')):
            rc, out = run('shopify theme push --theme %s --only sections/rewards-club.liquid '
                          '--nodelete%s' % (theme, extra), cwd=tw)
            print('  push %s: %s' % (theme, 'ok' if rc == 0 else 'FAILED\n' + out[-600:]))
            if rc != 0:
                return 2

    # Only advance the snapshot once everything above succeeded, so a failed run retries cleanly.
    json.dump(now, open(SNAPSHOT, 'w'), indent=1, sort_keys=True)
    with open(LOG, 'a') as f:
        f.write('\n### %s\n' % stamp + '\n'.join('- `%s`' % c for c in changes) + '\n')
    print('\nSnapshot advanced. Logged to %s' % os.path.basename(LOG))
    return 1


if __name__ == '__main__':
    sys.exit(main())
