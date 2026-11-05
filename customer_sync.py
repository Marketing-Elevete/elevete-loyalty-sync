#!/usr/bin/env python3
"""Nightly: copy voucher, can-claim and review data onto Shopify customer metafields (namespace `elevete`).

LoyaltyLion already writes Crumbs and tier fields itself (namespace `loyaltylion`); this adds what it does not.
Default is a dry run that writes nothing. Flags:
  --write            write the changes
  --only ID,ID       limit reading results and writes to these Shopify customer ids (test accounts)
  --setup            create the display settings for the fields first
Keys come from env, or the ~/. files on a Mac. State file holds what was last written, so only changes are sent.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.parse

SHOP = 'https://elevete-patisserie.myshopify.com/admin/api/2024-10/graphql.json'
LL = 'https://api.loyaltylion.com/v2'
KV = 'https://a.klaviyo.com/api'
STATE = os.environ.get('SYNC_STATE', 'customer_sync_state.json')
MYT = dt.timezone(dt.timedelta(hours=8))
VOUCHER_DAYS = 200   # ponytail: vouchers last about 3 months; widen if longer expiries are set
REVIEW_DAYS = 3      # catches a missed night or two

# ponytail: reward costs hard-coded for the "can claim" line; read the live catalogue if costs start changing
LADDER = [(1500, 'RM15 voucher'), (1200, 'Premium slice'), (1000, 'Free slice or RM10 voucher'), (500, 'RM5 voucher')]

FIELDS = [
    ('vouchers_available', 'Vouchers available', 'multi_line_text_field', 'Unused vouchers: amount, code, end date.'),
    ('vouchers_count', 'Vouchers count', 'number_integer', 'Unused vouchers on this account.'),
    ('vouchers_value', 'Vouchers value (RM)', 'number_integer', 'Total value of unused vouchers.'),
    ('voucher_next_end', 'Next voucher ends', 'date', 'End date of the voucher that ends first.'),
    ('can_claim', 'Can claim now', 'single_line_text_field', 'Best reward the Crumbs balance covers.'),
    ('reviews', 'Latest review per product', 'json', 'Product handle to latest review date. Used by the review list.'),
    ('data_changed', 'Rewards data last changed', 'date', 'When this job last changed the fields above.'),
]


def key(env, path):
    v = (os.environ.get(env) or '').strip()
    if v:
        return v
    return open(os.path.expanduser(path)).read().strip()


def curl(url, *args):
    for attempt in range(6):
        p = subprocess.run(['curl', '-sSg', '-m', '90', url, *args], capture_output=True, text=True)
        try:
            return json.loads(p.stdout)
        except ValueError:
            print('retry', attempt + 1, url.split('?')[0], 'curl exit', p.returncode, p.stderr[:120], flush=True)
            time.sleep(2 ** attempt)
    raise SystemExit('Bad response from %s: %s %s' % (url.split('?')[0], p.stdout[:160], p.stderr[:160]))


def gql(q, v=None):
    d = curl(SHOP, '-H', 'X-Shopify-Access-Token: ' + key('SHOPIFY_ADMIN_TOKEN', '~/.shopify_admin_token'),
             '-H', 'Content-Type: application/json', '-d', json.dumps({'query': q, 'variables': v or {}}))
    if d.get('errors'):
        if 'THROTTLED' in str(d['errors']):
            time.sleep(5)
            return gql(q, v)
        raise SystemExit('Shopify error: %s' % str(d['errors'])[:300])
    return d['data']


def ll_pages(path, list_key):
    base = LL + path
    url = base
    head = 'Authorization: Bearer ' + key('LOYALTYLION_HEADLESS_KEY', '~/.loyaltylion_key')
    while url:
        d = curl(url, '-H', head)
        yield from d.get(list_key, [])
        nxt = (d.get('cursor') or {}).get('next')
        url = base + ('&' if '?' in base else '?') + 'cursor=' + urllib.parse.quote(nxt) if nxt else None
        time.sleep(.15)


def can_claim(points, enrolled=True):
    for cost, label in LADDER:
        if (points or 0) >= cost:
            return label if enrolled else 'Join to use: ' + label
    return ''


def voucher_line(rm, code, ends):
    return 'RM%s  %s  ends %s' % (rm, code, ends.strftime('%-d %b %Y'))


def summarise(vouchers):
    """vouchers: list of (rm, code, end datetime in MYT). Soonest end first."""
    vs = sorted(vouchers, key=lambda v: v[2])
    return {
        'vouchers_available': '\n'.join(voucher_line(*v) for v in vs) or 'None',
        'vouchers_count': len(vs),
        'vouchers_value': sum(v[0] for v in vs),
        'voucher_next_end': vs[0][2].strftime('%Y-%m-%d') if vs else None,
    }


def merge_reviews(existing, new):
    out = dict(existing or {})
    for handle, day in new.items():
        if day > out.get(handle, ''):
            out[handle] = day
    return out


def unused_vouchers(only):
    """Customer id -> list of (rm, code, end). LoyaltyLion lists the claims; Shopify says if the code is still good."""
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=VOUCHER_DAYS)).strftime('%Y-%m-%dT00:00:00Z')
    now = dt.datetime.now(dt.timezone.utc)
    seen, out, checked = set(), {}, 0
    path = '/transactions?limit=500&created_at_min=' + urllib.parse.quote(since)
    for t in ll_pages(path, 'transactions'):
        c = t.get('claimed_reward') or {}
        code = (c.get('redeemable') or {}).get('code')
        cust = str((t.get('customer') or {}).get('merchant_id') or '')
        rm = (c.get('reward') or {}).get('discount_amount')
        if not code or not cust or not rm or code in seen or (only and cust not in only):
            continue
        seen.add(code)
        node = gql('query($c:String!){codeDiscountNodeByCode(code:$c){codeDiscount{... on DiscountCodeBasic'
                   '{status endsAt asyncUsageCount usageLimit}}}}', {'c': code})['codeDiscountNodeByCode']
        checked += 1
        d = (node or {}).get('codeDiscount') or {}
        if d.get('status') != 'ACTIVE' or (d.get('usageLimit') and d.get('asyncUsageCount', 0) >= d['usageLimit']):
            continue
        ends = d.get('endsAt') or (c.get('redeemable') or {}).get('expires_on')
        if not ends:
            continue
        end = dt.datetime.fromisoformat(ends.replace('Z', '+00:00'))
        if end > now:
            out.setdefault(cust, []).append((int(float(rm)), code, end.astimezone(MYT)))
    print('voucher codes checked', checked, 'customers with a live voucher', len(out), flush=True)
    return out


def balances(only, since=None):
    """Customer id -> can-claim line. With `since`, only customers changed after it: nightly runs stay short."""
    out = {}
    if only:    # test runs: no need to page through every member
        for cid in only:
            q = '{customer(id:"gid://shopify/Customer/%s"){metafield(namespace:"loyaltylion",key:"points_approved"){value}}}' % cid
            out[cid] = can_claim(int(((gql(q).get('customer') or {}).get('metafield') or {}).get('value') or 0))
        return out
    path = '/customers?limit=500'
    if since:
        path += '&updated_at_min=' + urllib.parse.quote(since)
    for c in ll_pages(path, 'customers'):
        m = str(c.get('merchant_id') or '')
        if m:
            out[m] = '' if c.get('blocked') else can_claim(c.get('points_approved'), c.get('enrolled'))
    print('LoyaltyLion customers read', len(out), flush=True)
    return out


def recent_reviews(only):
    """Customer id -> {product handle: YYYY-MM-DD}, from Klaviyo SubmittedReview."""
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=REVIEW_DAYS)).strftime('%Y-%m-%dT00:00:00Z')
    url = (KV + '/events/?filter=equals(metric_id,"UXXh2n"),greater-or-equal(datetime,%s)'
           '&include=profile&fields[event]=datetime,event_properties&fields[profile]=email&page[size]=200' % since)
    head = ['-H', 'Authorization: Klaviyo-API-Key ' + key('KLAVIYO_KEY', '~/.klaviyo_key'),
            '-H', 'revision: 2024-10-15', '-H', 'accept: application/json']
    by_email = {}
    while url:
        d = curl(url, *head)
        mail = {p['id']: p['attributes'].get('email') for p in d.get('included', [])}
        for e in d.get('data', []):
            em = mail.get(e['relationships']['profile']['data']['id'])
            handle = e['attributes']['event_properties'].get('product_handle')
            if em and handle:
                day = e['attributes']['datetime'][:10]
                by_email.setdefault(em.lower(), {})
                by_email[em.lower()][handle] = max(day, by_email[em.lower()].get(handle, ''))
        url = (d.get('links') or {}).get('next')
    out = {}
    for em, rev in by_email.items():
        q = 'query($q:String!){customers(first:1,query:$q){nodes{id metafield(namespace:"elevete",key:"reviews"){value}}}}'
        nodes = gql(q, {'q': 'email:"%s"' % em})['customers']['nodes']
        if not nodes:
            continue
        cid = nodes[0]['id'].split('/')[-1]
        if only and cid not in only:
            continue
        old = json.loads((nodes[0].get('metafield') or {}).get('value') or '{}')
        out[cid] = merge_reviews(old, rev)
    print('customers with a recent review', len(out), flush=True)
    return out


def setup():
    m = ('mutation($d:MetafieldDefinitionInput!){metafieldDefinitionCreate(definition:$d)'
         '{createdDefinition{name} userErrors{code message}}}')
    for k, name, ty, desc in FIELDS:
        r = gql(m, {'d': {'namespace': 'elevete', 'key': k, 'ownerType': 'CUSTOMER', 'type': ty, 'name': name,
                          'description': desc, 'pin': k != 'reviews'}})['metafieldDefinitionCreate']
        errs = [e for e in r['userErrors'] if e['code'] != 'TAKEN']
        print('definition', k, 'exists' if r['userErrors'] and not errs else 'created' if not errs else errs)


TYPES = {k: t for k, _, t, _ in FIELDS}


def to_inputs(cid, values):
    out = []
    for k, v in values.items():
        if v in (None, ''):
            continue
        out.append({'ownerId': 'gid://shopify/Customer/' + cid, 'namespace': 'elevete', 'key': k, 'type': TYPES[k],
                    'value': json.dumps(v) if TYPES[k] == 'json' else str(v)})
    return out


def diff(desired, state):
    """Only what changed. A customer who no longer has a value gets the empty form, so old data never lingers."""
    changes = {}
    empty = {'vouchers_available': 'None', 'vouchers_count': 0, 'vouchers_value': 0}
    for cid in set(desired) | set(state):
        new, old = desired.get(cid, {}), state.get(cid, {})
        delta = {k: v for k, v in new.items() if old.get(k) != v}
        for k in old:
            if k not in new and k in empty:
                delta[k] = empty[k]
        drop = [k for k in old if k not in new and k not in empty and k != 'reviews']
        if delta or drop:
            changes[cid] = (delta, drop)
    return changes


def main():
    write = '--write' in sys.argv
    only = set()
    if '--only' in sys.argv:
        only = set(sys.argv[sys.argv.index('--only') + 1].split(','))
    if '--setup' in sys.argv and write:
        setup()
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    if only:
        state = {k: v for k, v in state.items() if k in only}
    vouchers = unused_vouchers(only)
    since = None
    if state and not only:
        since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).strftime('%Y-%m-%dT00:00:00Z')
    claims = balances(only, since)
    reviews = recent_reviews(only)

    desired = {}
    for cid in set(vouchers) | set(claims) | set(reviews) | set(state):
        d = {}
        if vouchers.get(cid):
            d.update(summarise(vouchers[cid]))
        line = claims[cid] if cid in claims else state.get(cid, {}).get('can_claim')    # unchanged customers keep theirs
        if line:
            d['can_claim'] = line
        if d:
            desired[cid] = d
    for cid, rev in reviews.items():
        desired.setdefault(cid, {})['reviews'] = rev
    for cid, old in state.items():      # reviews accumulate; a night with no new review keeps them
        if old.get('reviews') and 'reviews' not in desired.get(cid, {}):
            desired.setdefault(cid, {})['reviews'] = old['reviews']

    changes = diff(desired, state)
    today = dt.datetime.now(MYT).strftime('%Y-%m-%d')
    print('customers to update', len(changes), 'fields', sum(len(a) + len(b) for a, b in changes.values()), flush=True)
    if not write:
        print('Dry run: nothing written. Sample of shapes:',
              {k: type(v).__name__ for k, v in (next(iter(desired.values()), {})).items()})
        return

    inputs = []
    for cid, (delta, drop) in changes.items():
        inputs += to_inputs(cid, dict(delta, data_changed=today))
        for k in drop:
            found = gql('{customer(id:"gid://shopify/Customer/%s"){metafield(namespace:"elevete",key:"%s"){id}}}' % (cid, k))
            mid = ((found.get('customer') or {}).get('metafield') or {}).get('id')
            if mid:
                gql('mutation($m:[MetafieldIdentifierInput!]!){metafieldsDelete(metafields:$m){userErrors{message}}}',
                    {'m': [{'ownerId': 'gid://shopify/Customer/' + cid, 'namespace': 'elevete', 'key': k}]})
    failed = 0
    m = 'mutation($m:[MetafieldsSetInput!]!){metafieldsSet(metafields:$m){userErrors{field message}}}'
    for i in range(0, len(inputs), 25):
        errs = gql(m, {'m': inputs[i:i + 25]})['metafieldsSet']['userErrors']
        if errs:
            failed += len(errs)
            print('write error', str(errs)[:240], flush=True)
        time.sleep(.25)
    if not only:
        json.dump(desired, open(STATE, 'w'))
    print('written fields', len(inputs) - failed, 'failed', failed, flush=True)
    if failed:
        sys.exit(1)     # fails the run, so GitHub sends its failure email


def demo():
    assert can_claim(1600) == 'RM15 voucher' and can_claim(499) == '' and can_claim(None) == ''
    assert can_claim(600, False) == 'Join to use: RM5 voucher'
    a = dt.datetime(2026, 11, 18, 23, 59, tzinfo=MYT)
    b = dt.datetime(2026, 12, 1, 23, 59, tzinfo=MYT)
    s = summarise([(10, 'B', b), (5, 'A', a)])
    assert s['vouchers_value'] == 15 and s['vouchers_count'] == 2 and s['voucher_next_end'] == '2026-11-18'
    assert s['vouchers_available'].startswith('RM5  A  ends 18 Nov 2026')
    assert summarise([])['vouchers_available'] == 'None'
    assert merge_reviews({'x': '2026-01-01'}, {'x': '2026-02-01', 'y': '2026-03-01'}) == {'x': '2026-02-01', 'y': '2026-03-01'}
    assert merge_reviews({'x': '2026-05-01'}, {'x': '2026-02-01'}) == {'x': '2026-05-01'}
    # voucher used since last night: back to the empty form. Balance fell below 500: the line is removed.
    delta, drop = diff({}, {'1': {'vouchers_count': 1, 'vouchers_available': 'x', 'vouchers_value': 5, 'can_claim': 'RM5 voucher'}})['1']
    assert delta == {'vouchers_available': 'None', 'vouchers_count': 0, 'vouchers_value': 0} and drop == ['can_claim']
    assert diff({'1': {'can_claim': 'x'}}, {'1': {'can_claim': 'x'}}) == {}
    print('self-check ok')


if __name__ == '__main__':
    demo() if '--check' in sys.argv else main()
