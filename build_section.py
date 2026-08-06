import os
#!/usr/bin/env python3
"""Generate sections/rewards-club.liquid — the custom Elevete rewards page as a
namespaced Shopify section, wired to live window.loyaltylion.customer (B-lite).
Verifiable locally via build_section_preview() which mocks the LL SDK."""
import json, html, re

cfg = json.load(open('/tmp/ll_config.json'))
img = json.load(open('flavour_images.json'))
def esc(s): return html.escape(str(s))
def fv(o): return (o.get('variants') or [{}])[0]

# ---------- data prep (baked catalog) ----------
EARN_ICONS={'purchase':'🛒','join_program':'🎁','newsletter_signup':'✉️','instagram_follow':'📸',
 'facebook_like':'👍','tiktok_follow':'🎵','birthday':'🎂','referral':'👯','custom':'⭐'}
# LoyaltyLion's own copy says "points"; the whole programme is branded "Crumbs". Leaving the raw
# text through made the earn tiles read "250 points" beside a page that says Crumbs everywhere,
# which looks like two different currencies. Normalise it at the source.
_crumbify = lambda t: re.sub(r'\bpoints?\b', lambda m: 'Crumbs' if m.group(0)=='points' else 'Crumb', t or '')
rules=[{'kind':r.get('kind'),'id':r.get('id'),'title':fv(r).get('title','') or '','text':_crumbify(fv(r).get('result_short_text','')),
        'icon':EARN_ICONS.get(r.get('kind'),'✨')} for r in cfg['rules']]
purchase=next((r for r in rules if r['kind']=='purchase'),None)
# Tiles cover the ways to earn that AREN'T already given their own surface:
#  - 'purchase' is the featured row above the tiles
#  - 'collection_purchase' (Flavour of the Month) has its own section, and its points value is
#    this month's number — baking it into a tile would go stale the moment the promo rotates
#  - 'referral' has the dedicated referral block with the actual link
SKIP_TILE={'purchase','collection_purchase','referral'}
# Rules the member cannot "claim" — they fire on their own. Showing a claim prompt on these
# is a false affordance, so they get a plain description of when they happen instead.
AUTO_KINDS={'join_program','birthday'}
AUTO_TEXT={'join_program':'Added when you join','birthday':'Lands on your birthday'}
other_earn=[r for r in rules if r['kind'] not in SKIP_TILE]
# The birthday reward is tier-scaled; the rule's own text only quotes the Foodie value.
for _r in other_earn:
    if _r['kind']=='birthday': _r['text']='RM5–RM15 by tier'

# Hero background. Shopify's CDN resizes and serves WebP when given a width param, so we ship a
# ~700px file to phones instead of the full PNG. fetchpriority=high + explicit dimensions so it
# loads first and reserves its own space (no CLS).
_hero_src = ((img.get('Black Forest') or {}).get('image') or '').split('&')[0]
HERO_IMG = _hero_src + ('&' if '?' in _hero_src else '?')
# Member hero uses a LIFESTYLE shot, not a studio cross-section: someone holding a cake out
# toward you is the whole feeling of a rewards page, and it's a different register from the
# guest hero so the two don't read as copy-paste. Because a lifestyle frame has a subject, it
# is NOT blurred and NOT used as full-bleed wallpaper — see the .s-mhero gradient, which goes
# fully opaque at 47% so the photo owns the top half and all the small type gets a clean ground.
_LIFESTYLE='https://cdn.shopify.com/s/files/1/0046/1969/8210/files/'
# Owner picked Sourdough Carrot (23 Jul): the rust cable-knit is the nearest thing in the set to
# our orange, so the balance figure sits INSIDE the photo's palette instead of on top of it.
MHERO_IMG = _LIFESTYLE + 'EP_Sourdough-carrot-cake_Lifestyle-1.png?'

FK=list(img.keys())
def match_img(t):
    tl=t.lower()
    for fl in FK:
        if fl.lower() in tl and img[fl] and img[fl].get('image'): return img[fl]['image']
    if 'popcorn' in tl: return (img.get('Popcorn') or {}).get('image')
    if 'salted caramel' in tl: return (img.get('Salted Caramel Chocolate') or {}).get('image')
    if 'tiramisu' in tl: return (img.get('Tiramisu') or {}).get('image')
    if 'tokeru' in tl: return (img.get('Tokeru') or {}).get('image')
    return None
# Earn rate per tier, read from the purchase rule's enabled variants rather than hardcoded.
_pr = next((r for r in cfg.get('rules', []) if r.get('kind') == 'purchase'), None)
_rate_by_tier = {}
for _v in ((_pr or {}).get('variants') or []):
    _res = _v.get('result') or {}
    if _v.get('enabled') and _res.get('points'):
        _rate_by_tier[_v.get('tier_id')] = _res['points']

vouchers,slices=[],[]
for r in cfg['rewards']:
    v=fv(r); title=v.get('title',''); pts=(v.get('cost',{}) or {}).get('points',0)
    if r.get('kind')=='cart_discount_voucher':
        vouchers.append({'id':r.get('id'),'amt':r.get('properties',{}).get('discount',{}).get('formatted',title),'pts':pts})
    else:
        # LoyaltyLion titles carry stray whitespace (" Pandan Gula Melaka…"), harmless in a block
        # element but visible the moment the name is concatenated into a sentence.
        clean=' '.join(title.replace('Free ','').replace(' [Premium]','').replace(' [Standard]','').split())
        slices.append({'id':r.get('id'),'title':clean,'pts':pts,'tier':'Premium' if '[Premium]' in title else 'Standard','img':match_img(title)})
vouchers.sort(key=lambda x:x['pts'])

# tier matrix (plain language)
TIER_META=[("Foodie","Join free"),("Indulgent","RM250 total spend"),("Connoisseur","RM1,000 total spend")]
RATE=[5,7,10]
# A string value renders as a NUMBER in the matrix instead of a tick — used where the perk
# scales by tier and the amount is the whole point (BloomThis-style: show the ladder, don't
# hide it behind three identical checkmarks).
# Ordered as a clean cascade so the ladder reads at a glance:
#   1. the three tier-scaled VALUE rows
#   2. everything every member gets  (✓ ✓ ✓)
#   3. Indulgent and above           (— ✓ ✓)
#   4. Connoisseur only              (— — ✓)
# The dashes then form a triangle in the bottom-left instead of being scattered.
# Note: Double Crumbs belongs in group 2 — rule 253052 is enabled for ALL THREE tiers
# (600/840/1,200 pts). Values aren't shown because they derive from this month's product price.
PERK_MATRIX=[
 ("Welcome gift when you arrive",["250 Crumbs","RM5","RM15"]),
 ("Birthday treat",["RM5","RM10","RM15"]),
 ("Shop sales before everyone",[1,1,1]),
 ("Members-only content",[1,1,1]),
 ("Double Crumbs on the monthly flavour",[1,1,1]),
 ("Preview new flavours first",[0,1,1]),
 ("Priority festive pre-orders",[0,1,1]),
 ("First dibs on limited editions",[0,0,1])]
COMING=[{'icon':'🧁','title':'Free Macaron Box','note':'A box of our signature macarons','tag':'In the works'},
 {'icon':'🎂','title':'Free Whole Celebration Cake','note':'The ultimate reward, for our most loyal','tag':'Coming soon'},
 {'icon':'✨','title':'Members-first flavour drops','note':'Taste new creations before anyone else','tag':'New perk'}]
# Every figure below is taken from the live LoyaltyLion config — if a rule or reward changes,
# update these too, or the page starts promising something the programme doesn't deliver.
FAQ=[("How does Elevete Fam work?","Every RM1 you spend earns Crumbs — save them up and swap them for a free cake slice or money off your order. Your tier is set by your total lifetime spend, so everything you've ever ordered already counts toward it, and the higher your tier the faster you earn. Your Crumbs balance starts building from your next order (see “I've been ordering for years…” below)."),
 ("How do I earn Crumbs?","Mainly by ordering: 5 Crumbs per RM1 in Foodie, 7 in Indulgent, 10 in Connoisseur. On top of that there are one-off bonuses for joining, signing up to our emails, following us and leaving a review — plus 1,000 Crumbs each time a friend you refer places their first order."),
 ("I've been ordering for years — why don't I have more Crumbs?","Your order history set your starting tier, so your years with us counted from day one — that's why you may already be Indulgent or Connoisseur, earning Crumbs faster than a new member. Crumbs themselves start adding up from your next order; past purchases don't convert into Crumbs, but they've already earned you your tier and its higher earn rate."),
 ("What do I get on my birthday?","A voucher sized to your tier: RM5 for Foodie, RM10 for Indulgent, RM15 for Connoisseur. It lands automatically on the day."),
 ("What is Flavour of the Month?","Each month we put one treat in the spotlight, and ordering it that month earns you double Crumbs. This month's pick is shown further up this page."),
 ("How do I redeem?","Pick any reward you can afford here and hit redeem — it applies to your next order at checkout. There's a small minimum order: RM50 for a free cake slice or the RM5 voucher, RM80 for the RM10 and RM15 vouchers."),
 ("Do my Crumbs expire?","From 31 March 2027, Crumbs expire after 12 months without any account activity — placing an order or redeeming a reward resets the clock. Redeemed rewards should be used within the window shown on the reward.")]

# ---------- namespace the proven prototype CSS under .rc-club (robust, tinycss2 AST) ----------
import tinycss2
raw=open('_proto_css.txt').read()

def transform_selector(sel):
    parts=[p.strip() for p in sel.split(',')]
    out=[]
    for p in parts:
        if not p: continue
        if p.startswith(':root'): out.append('.rc-club'+p[len(':root'):])
        elif p.startswith('body.v-member'): out.append('.rc-club.is-member'+p[len('body.v-member'):])
        elif p.startswith('body.v-guest'): out.append('.rc-club.is-guest'+p[len('body.v-guest'):])
        elif p=='body': out.append('.rc-club')
        elif p.startswith('body'): out.append('.rc-club'+p[len('body'):])
        elif p.startswith('.js'): out.append('.rc-club'+p)          # '.js .x' -> '.rc-club.js .x' (compound)
        elif p.startswith('#confetti'): out.append('#rc-confetti'+p[len('#confetti'):])
        else: out.append('.rc-club '+p)                             # descendant
    return ', '.join(out)

def render(nodes):
    buf=''
    for node in nodes:
        t=node.type
        if t=='qualified-rule':
            sel=tinycss2.serialize(node.prelude).strip()
            body=tinycss2.serialize(node.content)
            buf+=transform_selector(sel)+'{'+body+'}\n'
        elif t=='at-rule':
            kw=(node.lower_at_keyword or '')
            prelude=tinycss2.serialize(node.prelude).strip()
            if kw in ('media','supports') and node.content is not None:
                inner=tinycss2.parse_stylesheet(tinycss2.serialize(node.content), skip_comments=False, skip_whitespace=False)
                buf+='@'+node.at_keyword+' '+prelude+'{'+render(inner)+'}\n'
            elif node.content is not None:   # @keyframes, @font-face — keep body verbatim
                buf+='@'+node.at_keyword+' '+prelude+'{'+tinycss2.serialize(node.content)+'}\n'
            else:
                buf+='@'+node.at_keyword+' '+prelude+';\n'
        elif t=='comment':
            buf+='/*'+node.value+'*/'
        elif t=='whitespace':
            buf+=' '
    return buf

scoped_css=render(tinycss2.parse_stylesheet(raw, skip_comments=False, skip_whitespace=False))
# rename keyframes cleanly (one pass; originals are 'shine'/'fillpulse', never prefixed yet)
scoped_css=re.sub(r'\bshine\b','rc-shine',scoped_css)
scoped_css=re.sub(r'\bfillpulse\b','rc-fillpulse',scoped_css)
assert 'body.v-' not in scoped_css and '.rc-club .rc-club' not in scoped_css and '#confetti' not in scoped_css.replace('#rc-confetti',''), "scope sanity failed"

# --- REM -> PX (root-font-size immunity) -------------------------------------
# The Elevete theme sets a 10px root font-size (the "62.5%" trick), but the prototype
# was authored against the browser default of 16px. Left as-is, every rem in this
# section renders at 62.5% of its intended size and the whole type scale collapses.
# Converting to absolute px pins the section to the prototype's proportions regardless
# of what the theme does to the root. (Safe inside @media too: media-query rem is spec'd
# against the INITIAL 16px root, so the arithmetic is identical either way.)
_rem_count = len(re.findall(r'(?<![\w-])(\d*\.?\d+)rem', scoped_css))
scoped_css = re.sub(r'(?<![\w-])(\d*\.?\d+)rem',
                    lambda m: '%gpx' % (float(m.group(1)) * 16), scoped_css)
assert 'rem' not in re.sub(r'[\w-]*rem[\w-]+', '', scoped_css), "leftover bare rem after conversion"

# The theme styles bare h1-h4 (colour + family) and those rules beat our size-only
# heading rules, so headings rendered pure black instead of the warm ink. Pin colour
# and family on our own headings; more specific rules (e.g. .flavour__title) still win.
scoped_css += """
.rc-club h1,.rc-club h2,.rc-club h3,.rc-club h4{color:var(--ink);font-family:var(--display);letter-spacing:0}
.rc-club p,.rc-club li,.rc-club button,.rc-club input,.rc-club .btn{font-family:var(--body)}

/* The theme sets word-break:break-word globally, which snapped tier names mid-word
   ("Indulgen/t", "Connois/seur"). Restore normal breaking; overflow-wrap is kept as a
   safety net so a genuinely too-long string still wraps instead of overflowing. */
.rc-club,.rc-club *{word-break:normal;overflow-wrap:break-word}

/* "You're here" was rendering on ALL THREE tier columns (bug inherited from the
   prototype). Show it only on the member's current tier, and never to guests —
   .rc-club.is-member simply doesn't match in the guest view, so it stays hidden. */
/* Tier-scaled perk amounts in the matrix (e.g. birthday Crumbs). Same visual language as
   the earn-rate row — numbers are orange — so "a number here means it scales by tier". */
.rc-club .mx__amt{font-family:var(--display);font-size:15px;color:var(--orange);line-height:1.1}

/* Tile states. --todo and --auto are muted on purpose: they are statements of fact, not
   calls to action, so they must not compete with the real buttons on the page. */
.rc-club .tile__state--todo{color:var(--ink-soft)}
.rc-club .tile__state--auto{color:var(--lock)}

/* Hero photo + scrim. The cake shots are already on a purple backdrop, so a purple-weighted
   gradient sits naturally over them and gives the text a reliable contrast floor. Image is
   z-index -2, scrim -1, content above; `isolation` keeps that stacking local to the section. */
.rc-club .s-ghero{position:relative;overflow:hidden;isolation:isolate;padding:56px 0 64px}
.rc-club .ghero__bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:-2;
  filter:blur(3px) saturate(1.1);transform:scale(1.06)}
.rc-club .s-ghero::after{content:"";position:absolute;inset:0;z-index:-1;
  background:linear-gradient(180deg,rgba(20,18,16,.86) 0%,rgba(74,45,143,.88) 50%,rgba(20,18,16,.93) 100%)}
/* Invert the type for the dark scrim. The purple highlight would vanish on a purple ground,
   so it becomes the gold already used in the sticky bar. */
.rc-club .s-ghero .ghero h1{color:#fff}
/* Beats the prototype's `.ghero h1 .hl` (0,3,1) — a plain `.s-ghero .hl` (0,3,0) loses to it
   and the highlight stayed purple, i.e. invisible against a purple scrim. */
.rc-club .s-ghero .ghero h1 .hl{color:#FCD34D}
.rc-club .s-ghero .ghero__sub{color:rgba(255,255,255,.88)}
.rc-club .s-ghero .eyebrow{color:#FCD34D}
.rc-club .s-ghero .ghero__stats{border-color:rgba(255,255,255,.28)}
/* Social proof at the decision point — bandwagon + "is this worth it" reassurance, right under
   the Join CTA. "19,000+" rounds down from ~19,241 enrolled, so it stays true as the base grows. */
.rc-club .s-ghero .ghero__social{margin-top:14px;font-size:14px;color:rgba(255,255,255,.9)}
.rc-club .s-ghero .ghero__social b{color:#FCD34D;font-family:var(--display);font-weight:400}
.rc-club .s-ghero .ghero__stats li{border-color:rgba(255,255,255,.28)}
.rc-club .s-ghero .ghero__stats b{color:#FCD34D}
.rc-club .s-ghero .ghero__stats span{color:rgba(255,255,255,.82)}
.rc-club .s-ghero .btn--ghost{border-color:rgba(255,255,255,.9);color:#fff}
.rc-club .s-ghero .btn--ghost:hover{background:rgba(255,255,255,.12)}

/* Even out the headline's line lengths so it never orphans a single word on the last line.
   Purely a rendering hint — no cost, ignored gracefully where unsupported. */
.rc-club .ghero h1{text-wrap:balance}
.rc-club .ghero__sub{text-wrap:balance}

/* Hero stat strip. Three equal fields with hairline dividers — the numbers do the selling,
   the labels just caption them. Stays 3-up even on a 360px screen because every value is short.
   No images, no motion: this is above the fold and must not touch LCP. */
.rc-club .ghero__stats{display:grid;grid-template-columns:repeat(3,1fr);margin:22px auto 24px;max-width:440px;
  border-top:1px solid rgba(74,45,143,.15);border-bottom:1px solid rgba(74,45,143,.15)}
.rc-club .ghero__stats li{list-style:none;padding:13px 6px;text-align:center;border-left:1px solid rgba(74,45,143,.15)}
.rc-club .ghero__stats li:first-child{border-left:0}
.rc-club .ghero__stats b{display:block;font-family:var(--display);font-size:21px;color:var(--orange);line-height:1.1}
.rc-club .ghero__stats span{display:block;font-size:11px;color:var(--ink-soft);margin-top:5px;line-height:1.35}
@media(min-width:640px){
  .rc-club .ghero__stats b{font-size:24px}
  .rc-club .ghero__stats span{font-size:12px}
}

/* Guest sticky CTA. Starts off-screen and slides up once the hero has scrolled away, so it
   never sits on top of the hero's own button. transform+opacity only — no layout, no repaint
   cost, and it respects reduced-motion by simply appearing. */
.rc-club .sticky--guest{transform:translateY(110%);opacity:0;transition:transform .28s cubic-bezier(.23,1,.32,1),opacity .28s ease-out;pointer-events:none}
.rc-club .sticky--guest.is-on{transform:translateY(0);opacity:1;pointer-events:auto}
@media (prefers-reduced-motion: reduce){
  .rc-club .sticky--guest{transition:none}
}
/* The guest page also needs the bottom breathing room the member bar gets. */
.rc-club.is-guest{padding-bottom:76px}
@media(min-width:900px){.rc-club.is-guest{padding-bottom:0}}

/* Tier calculator (guest). No images, no network. min-height on the output prevents any
   layout shift as the text changes length, so this costs nothing in CLS. */
.rc-club .calc{max-width:520px;margin:0 auto;text-align:center}
.rc-club .calc__spend{display:block;font-family:var(--display);font-size:40px;color:var(--orange);line-height:1.1;margin-bottom:14px}
.rc-club .calc__range{width:100%;-webkit-appearance:none;appearance:none;height:6px;border-radius:999px;background:rgba(74,45,143,.18);outline:none}
.rc-club .calc__range::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:30px;height:30px;border-radius:50%;background:var(--orange);border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.2);cursor:pointer}
.rc-club .calc__range::-moz-range-thumb{width:30px;height:30px;border:3px solid #fff;border-radius:50%;background:var(--orange);cursor:pointer}
.rc-club .calc__range:focus-visible{outline:2px solid var(--purple);outline-offset:4px}
.rc-club .calc__scale{display:flex;justify-content:space-between;font-size:12px;color:var(--lock);margin:8px 2px 20px}
.rc-club .calc__out{background:#fff;border:1.5px solid var(--purple);padding:18px;min-height:112px;display:flex;flex-direction:column;justify-content:center;gap:6px}
.rc-club .calc__tier{font-family:var(--display);font-size:21px;color:var(--purple)}
.rc-club .calc__detail{font-size:14px;color:var(--ink-soft);line-height:1.5}
.rc-club .calc__detail b{color:var(--ink)}
.rc-club .calc__cta{margin-top:14px;display:inline-block}
@media(max-width:520px){.rc-club .calc__out{min-height:128px}}

/* Guest reward wall: show a taste, not all 15 flavours. Shortens the path to the CTA on
   mobile and keeps the hidden cards' lazy images from ever being fetched. */
.rc-club.is-guest .cards:not(.show-all) .card:nth-of-type(n+4){display:none}
/* Members saw all 15 flavours — a 3,591px wall, 38% of the whole page, that buried Flavour of the
   Month and the tier matrix below it. Six is three rows on mobile. Safe to apply immediately
   (rather than waiting for the SDK) because render() reorders claimable-first WITHIN the grid:
   the visible COUNT never changes, so the six cards swap identity without shifting layout. The
   nine hidden ones also never fetch their images, since a display:none card never enters the
   viewport for the lazy loader. */
.rc-club.is-member .cards:not(.show-all) .card:nth-of-type(n+7){display:none}
/* LOCKED vs UNLOCKED, made unmistakable.
   The old lock rule was `.rc-club.is-member .card.is-lock{opacity:.82}` — same specificity (0,4,0)
   as `.rc-club.js .reveal.in{opacity:1}` from the reveal animation, which comes LATER in the
   sheet and therefore won. The card dimming never applied at all; only the image grayscale did.
   Fixed by dimming with `filter`, which the reveal system doesn't touch, so the two can't collide
   again. Also pushed much harder than the old 35% — a locked reward should read as locked at a
   glance, and snap to full colour the moment the member can afford it (render() toggles the
   class in both directions, so it unlocks live as the balance grows). */
.rc-club.is-member .card.is-lock,.rc-club.is-member .vcard.is-lock{filter:grayscale(.72) opacity(.62)}
.rc-club.is-member .card.is-lock .card__img img{filter:grayscale(.9)}
.rc-club.is-member .card.is-ok,.rc-club.is-member .vcard.is-ok{filter:none}
/* The claimable ones earn a quiet ring, so "you can have this now" is visible without reading. */
.rc-club.is-member .card.is-ok{outline:1.5px solid var(--orange);outline-offset:-1.5px}
/* Top-RIGHT: top-left already belongs to the Standard/Premium badge and the two collided. */
.rc-club .card__lock{position:absolute;top:8px;right:8px;z-index:2;background:rgba(20,18,16,.72);
  color:#fff;font-size:11px;font-weight:700;padding:3px 7px;line-height:1.3;display:none}
.rc-club.is-member .card.is-lock .card__lock,.rc-club.is-member .vcard.is-lock .card__lock{display:block}
.rc-club .card__img{position:relative}

/* "You're in the top N%" — the only status signal on the page that isn't about money. Percentiles
   come from the REAL lifetime-spend distribution of 78,652 buyers (Foodie 61,592 / Indulgent
   15,451 / Connoisseur 1,609, pulled 23 Jul), so the claim is true rather than flattering. */
.rc-club .mx-rank{max-width:640px;margin:18px auto 0;text-align:center;font-size:15px;
  font-weight:700;color:var(--purple)}
.rc-club .mx-rank b{color:var(--orange);font-family:var(--display);font-weight:400}

/* Voucher stand-in for the best-treat thumbnail — the slot is 72px and a voucher has no photo,
   so it drew an empty box that read as a broken image. */
/* Doubled class: `.best__img` sets a cream background at (0,2,0) and is declared later in the
   sheet, so a plain `.best__img--v` tied and lost — white text on cream. */
.rc-club .best__img.best__img--v{background:var(--purple)}
.rc-club .best__vouch{display:flex;flex-direction:column;align-items:center;justify-content:center;
  width:100%;height:100%;color:#fff;font-family:var(--display);font-size:18px;line-height:1}
.rc-club .best__vouch em{font-family:var(--body);font-style:normal;font-weight:700;font-size:10px;
  letter-spacing:.1em;text-transform:uppercase;color:#FCD34D;margin-top:3px}

/* PICK YOUR GOAL. Browsing 18 rewards is passive; committing to one is not. The star sets a
   target, and from then on the nudge, its progress bar and the sticky bar all point at THAT
   reward instead of whichever happens to be nearest — three signals aimed at one thing.
   Held in localStorage, so no backend and nothing to break. */
.rc-club .goal{display:inline-flex;align-items:center;gap:6px;margin-top:8px;padding:6px 0;
  background:none;border:0;font-family:var(--body);font-weight:700;font-size:11px;
  letter-spacing:.04em;text-transform:uppercase;color:var(--lock);cursor:pointer}
.rc-club .goal:hover,.rc-club .goal:focus-visible{color:var(--purple)}
.rc-club .goal__i{font-size:15px;line-height:1}
.rc-club .vcard .goal{color:rgba(255,255,255,.6)}
.rc-club .vcard .goal:hover,.rc-club .vcard .goal:focus-visible{color:#fff}
.rc-club .card.is-goal .goal,.rc-club .vcard.is-goal .goal{color:var(--orange)}
.rc-club .vcard.is-goal .goal{color:#FCD34D}
/* The chosen reward stays legible even while locked — it's the one card that must not fade out. */
.rc-club.is-member .card.is-goal,.rc-club.is-member .vcard.is-goal{filter:none;
  outline:2px solid var(--orange);outline-offset:-2px}
.rc-club.is-member .card.is-goal .card__img img{filter:none}
/* Vouchers have no .card__img, so the flag lands on the vcard itself — which needs to be a
   positioned ancestor, or the flag escapes and pins itself to the section corner. */
.rc-club .vcard{position:relative}
.rc-club .goal__flag{position:absolute;top:8px;right:8px;z-index:3;background:var(--orange);
  color:#fff;font-size:11px;font-weight:700;padding:3px 7px;line-height:1.3}

/* A locked reward said "100 Crumbs to go" and nothing else — a number the member has to convert
   into an action on their own. Tapping now answers it in ringgit at THEIR earn rate. The dotted
   underline is the affordance; without it nobody discovers the tap. */
.rc-club .rc__go--tap{cursor:pointer;border-bottom:1px dotted var(--lock);
  -webkit-tap-highlight-color:transparent}
.rc-club .rc__go--tap:hover,.rc-club .rc__go--tap:focus-visible{color:var(--purple);border-bottom-color:var(--purple)}
.rc-club .vcard .rc__go--tap:hover,.rc-club .vcard .rc__go--tap:focus-visible{color:#fff;border-bottom-color:#fff}
.rc-club .rc__go--plan{color:var(--orange);border-bottom-style:solid;border-bottom-color:var(--orange)}
.rc-club .vcard .rc__go--plan{color:#FCD34D;border-bottom-color:#FCD34D}
.rc-club .cards__more{margin:18px auto 0;display:block}

/* MEMBER HERO PHOTOGRAPH. This was the only hero on the page with no image — the guest got a
   cake and the member got a bank statement. Same proven technique as the guest hero (Shopify CDN
   WebP via &width=, explicit dimensions, fetchpriority high), which measured LCP 554→432ms and
   CLS 0.08→0.02 rather than costing anything. Scrim runs light-to-dark downward because the tier
   tracker sits at the bottom and needs the most contrast; the greeting at the top needs least. */
.rc-club .s-mhero{position:relative;overflow:hidden;isolation:isolate}
/* Deliberately NOT blurred. The guest hero blurs its cross-section because that shot is texture;
   this one has a person in it, and blurring a subject just makes it look like a mistake. */
/* The source is square and the hero is portrait, so it fits vertically exactly — which means
   object-position does NOTHING here and the cake stays buried under the opaque half of the scrim.
   A small upward transform is what actually lifts it into view. -6% is the balance point: any
   further and the pale frosting slides under the balance figure and kills the orange's contrast. */
.rc-club .mhero__bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;
  object-position:center;z-index:-2;filter:saturate(1.06);transform:translateY(-6%) scale(1.14)}
/* Splits the hero rather than veiling it. The photo owns the top half — eyebrow, greeting and the
   balance figure all sit on it happily, being large and high-contrast — then the scrim reaches
   FULL opacity at 47%, so the tier tracker's 11-13px text lands on flat black instead of on
   popcorn. Tried it as a straight wallpaper first and the tracker was unreadable. */
/* EASED, not linear. A 3-4 stop gradient interpolates alpha in a straight line and the eye reads
   that as a band with a visible edge — the cake looked cut off rather than faded. These 11 stops
   trace a smoothstep curve (e = p²(3-2p)) from .26 to fully opaque across 14%→56%, so the photo
   dissolves into the ground. Regenerate with the one-liner in the runbook if the range changes. */
.rc-club .s-mhero::after{content:"";position:absolute;inset:0;z-index:-1;
  background:linear-gradient(180deg,rgba(20,18,16,.26) 0%,
    rgba(20,18,16,0.260) 14.0%,rgba(20,18,16,0.281) 18.2%,rgba(20,18,16,0.337) 22.4%,
    rgba(20,18,16,0.420) 26.6%,rgba(20,18,16,0.520) 30.8%,rgba(20,18,16,0.630) 35.0%,
    rgba(20,18,16,0.740) 39.2%,rgba(20,18,16,0.840) 43.4%,rgba(20,18,16,0.923) 47.6%,
    rgba(20,18,16,0.979) 51.8%,rgba(20,18,16,1.000) 56.0%,#141210 100%)}
.rc-club .s-mhero .mhero{background:none}
/* Invert every piece of type for the dark ground. Purple dies on this scrim, so it becomes the
   same gold the guest hero and sticky bar already use; the balance stays brand orange. */
.rc-club .s-mhero .eyebrow{color:#FCD34D}
.rc-club .s-mhero .mhero__hi{color:#fff}
.rc-club .s-mhero .mhero__unit{color:rgba(255,255,255,.78)}
/* "What your balance is actually worth" — sits directly under the number so the translation is
   read in the same glance, not hunted for. */
.rc-club .mhero__worth{max-width:360px;margin:-20px auto 20px;font-size:15px;line-height:1.45;
  color:rgba(255,255,255,.92);text-wrap:balance}
/* Claw back the height this line costs, so the primary CTA stays above the sticky bar. */
.rc-club .s-mhero .mhero{padding-top:38px}
.rc-club .mhero__worth b{color:#FCD34D;font-family:var(--display);font-weight:400}
.rc-club .s-mhero .track__head{color:#fff}
.rc-club .s-mhero .track__head b{color:#FCD34D}
.rc-club .s-mhero .track__goal{color:rgba(255,255,255,.85)}
.rc-club .s-mhero .track__goal b{color:#FCD34D}
.rc-club .s-mhero .track__unlock{color:rgba(255,255,255,.92)}
.rc-club .s-mhero .track__unlock b{color:#FCD34D}
.rc-club .s-mhero .track__bar{background:rgba(255,255,255,.24)}
.rc-club .s-mhero .track__stop i{background:#2a2621;border-color:rgba(255,255,255,.42)}
.rc-club .s-mhero .track__stop--done i{background:var(--orange);border-color:var(--orange)}
.rc-club .s-mhero .track__stop em{color:rgba(255,255,255,.72)}
.rc-club .s-mhero .track__stop--done em{color:#fff}
.rc-club .s-mhero .track__note{color:rgba(255,255,255,.66);opacity:1}
.rc-club .s-mhero .mhero__since{background:rgba(255,255,255,.16);color:#fff}
.rc-club .s-mhero .mhero__since b{color:#FCD34D}
.rc-club .s-mhero .btn--ghost{border-color:rgba(255,255,255,.55);color:#fff}

/* Crumbs-expiry warning — the loss-aversion lever. Amber, sits under the balance. Only ever
   rendered when real points are within ~60 days of expiring (data-driven from pointsExpiringNext),
   so it is honest urgency, never fabricated. Dormant until the 12-mo-inactivity clock produces a
   real expiry date. */
.rc-club .mhero__expiry{background:rgba(252,211,77,.16);border:1px solid rgba(252,211,77,.55);
  color:#fff;padding:9px 14px;margin:0 0 14px;font-size:13.5px;line-height:1.4;border-radius:4px}
.rc-club .mhero__expiry b{color:#FCD34D;font-family:var(--display);font-weight:400}

/* Tier-up banner. The rarest thing that happens on this page — 5,196 crossings into Indulgent
   a year and 264 into Connoisseur — so it earns the one solid-orange moment in the hero and
   outranks the "+X Crumbs" pill when both would fire. */
.rc-club .mhero__tierup{background:var(--orange);color:#fff;padding:11px 16px;margin:0 0 12px;
  font-size:14px;line-height:1.4;border-radius:4px}
.rc-club .mhero__tierup b{color:#fff;font-family:var(--display)}

/* "Since your last visit" pill — small, celebratory, sits under the greeting. */
.rc-club .mhero__since{background:rgba(232,98,42,.12);color:var(--ink);border-radius:999px;
  padding:6px 14px;font-size:13px;margin-top:8px}
.rc-club .mhero__since b{color:var(--orange);font-family:var(--display)}

/* "Your best treat right now" — the one-tap redeem card. */
.rc-club .best{align-items:center;gap:16px;background:#fff;border:1.5px solid var(--orange);
  padding:14px 16px;margin:0 0 20px;flex-wrap:wrap}
.rc-club .best__img{flex:0 0 72px;height:72px;overflow:hidden;background:var(--cream-2)}
.rc-club .best__img img{width:100%;height:100%;object-fit:cover;display:block}
.rc-club .best__body{flex:1;min-width:180px}
.rc-club .best__eyebrow{display:block;font-size:11px;font-weight:700;letter-spacing:.14em;
  text-transform:uppercase;color:var(--orange);margin-bottom:3px}
.rc-club .best__title{font-family:var(--display);font-size:18px;color:var(--purple);line-height:1.2}
.rc-club .best__note{font-size:13px;color:var(--ink-soft);margin-top:3px}
.rc-club .best__cta{white-space:nowrap}
@media(max-width:560px){
  .rc-club .best{gap:12px}
  .rc-club .best__cta{width:100%}
}

/* Referral block */
.rc-club .refer{background:#fff;border:1.5px solid var(--purple);padding:20px;margin-top:24px}
.rc-club .refer__top{display:flex;gap:14px;align-items:flex-start;margin-bottom:16px}
.rc-club .refer__icon{font-size:30px;line-height:1}
.rc-club .refer__title{font-family:var(--display);font-size:19px;color:var(--purple);margin-bottom:6px}
.rc-club .refer__how{font-size:14px;color:var(--ink-soft);line-height:1.5}
.rc-club .refer__how b{color:var(--ink)}
.rc-club .refer__row{display:flex;gap:8px;flex-wrap:wrap}
.rc-club .refer__link{flex:1;min-width:200px;border:1.5px solid var(--cream-2);background:var(--cream);padding:12px 14px;font-family:var(--body);font-size:14px;color:var(--ink);overflow:hidden;text-overflow:ellipsis}
.rc-club .refer__copy{white-space:nowrap}
.rc-club .refer__wa{display:inline-block;margin-top:10px;font-weight:700;font-size:15px;color:var(--purple);text-decoration:underline}
.rc-club .refer__fine{margin-top:10px;font-size:12px;color:var(--lock)}
@media(max-width:520px){.rc-club .refer__row{flex-direction:column}.rc-club .refer__copy{width:100%}}
.rc-club .mx__head .mx__here{display:none}
.rc-club.is-member .mx__head.is-cur .mx__here{display:block}
"""
print("rem->px conversions:", _rem_count)

# ---------- HTML builders (baked) ----------
def voucher_card(v, ordi=0):
    return f'''<div class="vcard" data-rid="{v['id']}" data-ord="{ordi}" data-cost="{v['pts']}" data-name="a {esc(v['amt'])} voucher">
      <span class="vcard__amt">{esc(v['amt'])}</span><span class="vcard__sub">off your order</span>
      <span class="vcard__pts">{v['pts']} Crumbs</span>
      <span class="rc__go only-member" data-lion-account-link="redeem"></span><button class="goal only-member" type="button" data-goal aria-pressed="false" title="Set as my goal"><span class="goal__i" aria-hidden="true">☆</span><span class="goal__t">Set as my goal</span></button></div>'''
def slice_card(s, ordi=0):
    imgtag=f'<img src="{esc(s["img"])}" alt="{esc(s["title"])}" loading="lazy" width="400" height="400">' if s['img'] else '<div class="ph"></div>'
    tb=f'<span class="card__tier card__tier--{s["tier"].lower()}">{s["tier"]}</span>'
    return f'''<div class="card" data-rid="{s['id']}" data-ord="{ordi}" data-cost="{s['pts']}" data-name="a free {esc(s['tier'])} cake slice">
      <div class="card__img">{imgtag}{tb}<span class="card__lock only-member">🔒 Locked</span></div>
      <div class="card__body"><h4 class="card__title">{esc(s['title'])}</h4>
      <span class="card__pts">{s['pts']} Crumbs</span>
      <span class="rc__go only-member" data-lion-account-link="redeem"></span><button class="goal only-member" type="button" data-goal aria-pressed="false" title="Set as my goal"><span class="goal__i" aria-hidden="true">☆</span><span class="goal__t">Set as my goal</span></button></div></div>'''
def earn_tile(r, extra_cls=''):
    auto=' data-auto="1"' if r['kind'] in AUTO_KINDS else ''
    return f'''<div class="tile{extra_cls}" data-kind="{r['kind']}"{auto}><span class="tile__icon">{r['icon']}</span>
      <span class="tile__label">{esc(r['title'])}</span><span class="tile__pts">{esc(r['text'])}</span>
      <span class="tile__state only-member"></span></div>'''

# Referral is skipped from the tiles because members get the dedicated block with their actual
# link — but that block is `only-member`, so GUESTS were never told that referring earns 1,000
# Crumbs, the single biggest earn action on the programme and the one that brings new customers.
# Give guests a tile, first in the list because it is worth the most. Members still get the block.
_ref=next((r for r in rules if r['kind']=='referral'),None)
referral_tile=earn_tile(_ref,' only-guest') if _ref else ''

vouchers_html=''.join(voucher_card(v,i) for i,v in enumerate(vouchers))
slices_html=''.join(slice_card(s,i) for i,s in enumerate(slices))
other_tiles=referral_tile+''.join(earn_tile(r) for r in other_earn)
coming_html=''.join(f'<div class="soon"><span class="soon__badge">{esc(c["tag"])}</span><span class="soon__icon">{c["icon"]}</span><h4 class="soon__title">{esc(c["title"])}</h4><p class="soon__note">{esc(c["note"])}</p></div>' for c in COMING)
faq_html=''.join(f'<details class="faq__item"><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q,a in FAQ)

# matrix
CUR_IDX=0  # JS re-highlights the real current tier
def _cur(i): return ' is-cur' if i==CUR_IDX else ''
_hdr='<div class="mx__cell mx__corner"></div>'
for i,(nm,how) in enumerate(TIER_META):
    _hdr+=f'<div class="mx__cell mx__head" data-tier="{i}"><span class="mx__here only-member">You\'re here</span><span class="mx__tname">{nm}</span><span class="mx__how">{how}</span></div>'
_rate='<div class="mx__cell mx__lbl">Crumbs earned per RM1</div>'+''.join(f'<div class="mx__cell mx__val" data-tier="{i}"><span class="mx__rate">{r}×</span></div>' for i,r in enumerate(RATE))
_prows=''; _d=0
for label,has in PERK_MATRIX:
    _prows+=f'<div class="mx__cell mx__lbl">{esc(label)}</div>'
    for i,h in enumerate(has):
        if isinstance(h,str):
            mark=f'<span class="mx__amt">{esc(h)}</span>'
        else:
            mark=(f'<span class="mx__check" style="--d:{_d*0.035:.2f}s">✓</span>' if h else '<span class="mx__no">–</span>')
        _prows+=f'<div class="mx__cell mx__val" data-tier="{i}">{mark}</div>'; _d+=1
matrix_html=f'<div class="mx">{_hdr}{_rate}{_prows}</div>'

# ---------- the section markup (member fields are JS-populated placeholders) ----------
MARKUP=f'''<div class="rc-club is-guest">
<div class="wrap">

<!-- MEMBER HERO (populated from window.loyaltylion.customer) -->
<section class="s-mhero only-member">
<img class="mhero__bg" alt="" aria-hidden="true" decoding="async" fetchpriority="high" width="1400" height="933"
  src="{MHERO_IMG}width=1400"
  srcset="{MHERO_IMG}width=700 700w, {MHERO_IMG}width=1000 1000w, {MHERO_IMG}width=1400 1400w" sizes="100vw"><!--/mhero-img-->
<div class="mhero">
  <span class="eyebrow">Elevete Fam</span>
  <div class="mhero__tierup only-member" data-ll="tierup" style="display:none"></div>
  <p class="mhero__hi">Welcome back, <span data-ll="firstName">there</span></p>
  <div class="mhero__since only-member" data-ll="since" style="display:none"></div>
  <div class="mhero__bal"><span class="mhero__num" data-ll="points">0</span><span class="mhero__unit">Crumbs to spend</span></div>
  <p class="mhero__worth only-member" data-ll="worth" style="display:none"></p>
  <div class="mhero__expiry only-member" data-ll="expiry" style="display:none"></div>
  <div class="track"><div class="track__head">
    <span>You're in <b data-ll="tier">Foodie</b></span>
    <span class="track__goal" data-ll="goal"></span>
    <span class="track__unlock" data-ll="unlock"></span></div>
    <div class="track__bar"><div class="track__fill" data-ll="fill" style="width:0%"></div>
      <span class="track__stop track__stop--first" data-stop="0" style="left:0%"><i></i><em>Foodie<br>RM0</em></span>
      <span class="track__stop" data-stop="1" style="left:50%"><i></i><em>Indulgent<br>RM250</em></span>
      <span class="track__stop track__stop--last" data-stop="2" style="left:100%"><i></i><em>Connoisseur<br>RM1,000</em></span></div>
    <p class="track__note">Your tier is based on your total spend with Elevete — everything you've ever ordered counts.</p></div>
  <div class="cta-row"><a class="btn btn--primary" data-lion-account-link="redeem" href="#rc-treats">Redeem your Crumbs</a><a class="btn btn--ghost" href="#rc-earn">Ways to earn more</a></div>
</div></section>

<!-- MEMBER SIMULATOR. Guests get a tier calculator to play with and members got nothing — the
     one interactive thing on the page was for people who hadn't joined. This is its member
     counterpart: it answers "what would an order actually get me?" using THEIR earn rate, their
     real balance and the real catalogue, so the answer is theirs and not an average. Reuses the
     .calc classes wholesale, so it costs no new layout CSS. -->
<section class="section s-msim only-member">
  <div class="section__head"><span class="eyebrow">Plan ahead</span><h2>What would your next order earn?</h2>
    <p>Drag to whatever you&rsquo;re thinking of spending.</p></div>
  <div class="calc">
    <output class="calc__spend" data-sim="spend">RM150</output>
    <input class="calc__range" type="range" min="0" max="600" step="10" value="150"
           id="rc-sim-range" name="rc-sim-range" data-sim="range"
           aria-label="How much you are thinking of spending">
    <div class="calc__scale"><span>RM0</span><span>RM300</span><span>RM600</span></div>
    <div class="calc__out">
      <div class="calc__tier" data-sim="earn"></div>
      <div class="calc__detail" data-sim="detail"></div>
    </div>
  </div>
</section>

<!-- GUEST HERO -->
<section class="s-ghero only-guest">
<img class="ghero__bg" alt="" aria-hidden="true" decoding="async" fetchpriority="high" width="1400" height="933"
  src="{HERO_IMG}width=1400"
  srcset="{HERO_IMG}width=700 700w, {HERO_IMG}width=1000 1000w, {HERO_IMG}width=1400 1400w" sizes="100vw"><!--/ghero-img-->
<div class="ghero">
  <span class="eyebrow">Elevete Fam</span>
  <h1>Everything you've <span class="hl">already ordered</span> counts</h1>
  <p class="ghero__sub">Join free. Every RM1 you&rsquo;ve ever spent counts toward your tier.</p>
  <ul class="ghero__stats">
    <li><b>250</b><span>Crumbs the moment you join</span></li>
    <li><b>5&ndash;10</b><span>Crumbs per RM1 you spend</span></li>
    <li><b>1,000</b><span>Crumbs = a free cake slice</span></li>
  </ul>
  <div class="cta-row"><a class="btn btn--primary" href="/account/register">Join Elevete Fam</a><a class="btn btn--ghost" href="/account/login">Log in</a></div>
  <p class="ghero__social">Join <b>19,000+</b> Elevete regulars — it&rsquo;s free and takes a minute.</p>
</div></section>

<!-- TIER CALCULATOR (guest) — pays off the hero's claim with THEIR number.
     Pure CSS + a few lines of vanilla JS: no images, no network, nothing runs until the
     slider is touched, and the output box has a min-height so updating it can't shift layout. -->
<section class="section s-calc only-guest">
  <div class="section__head"><span class="eyebrow">Find out</span><h2>Where would you land?</h2>
    <p>Drag to roughly what you&rsquo;ve spent with Elevete over the years.</p></div>
  <div class="calc">
    <output class="calc__spend" data-calc="spend">RM400</output>
    <input class="calc__range" type="range" min="0" max="2000" step="50" value="400"
           id="rc-calc-range" name="rc-calc-range" data-calc="range"
           aria-label="Roughly how much you have spent with Elevete">
    <div class="calc__scale"><span>RM0</span><span>RM1,000</span><span>RM2,000</span></div>
    <div class="calc__out">
      <div class="calc__tier">You&rsquo;d be <b data-calc="tier">Indulgent</b></div>
      <div class="calc__detail" data-calc="detail"></div>
    </div>
    <a class="btn btn--primary calc__cta" href="/account/register">Join and claim your tier</a>
  </div>
</section>

<!-- HOW IT WORKS (guest) -->
<section class="section section--tint s-how only-guest">
  <div class="section__head"><span class="eyebrow">Three steps</span><h2>How it works</h2></div>
  <div class="steps">
    <div class="step"><span class="step__n">01</span><div><div class="step__t">Join free</div><div class="step__d">Takes a minute. We'll add 250 Crumbs to your account straight away, and everything you've ordered before counts toward your tier.</div></div></div>
    <div class="step"><span class="step__n">02</span><div><div class="step__t">Earn as you order</div><div class="step__d">Every RM1 earns 5 to 10 Crumbs depending on your tier. Your birthday, referrals and reviews earn more on top.</div></div></div>
    <div class="step"><span class="step__n">03</span><div><div class="step__t">Spend them on cake</div><div class="step__d">Swap them for a free cake slice, or take RM off your order instead. Your call.</div></div></div>
  </div>
</section>

<!-- REDEEM -->
<section class="section section--tint s-treats" id="rc-treats">
  <div class="section__head"><span class="eyebrow">Redeem</span><h2>Treats worth craving</h2>
    <p>Every <b>100 Crumbs is worth RM1</b>.</p></div>
  <p class="afford-note only-member" data-ll="afford"></p>
  <div class="best only-member" data-ll="best" style="display:none">
    <div class="best__img" data-ll="bestImg"></div>
    <div class="best__body">
      <span class="best__eyebrow">Ready for you</span>
      <h3 class="best__title" data-ll="bestTitle"></h3>
      <p class="best__note" data-ll="bestNote">You have enough Crumbs. Claim it whenever you like.</p>
    </div>
    <a class="btn btn--primary best__cta" data-lion-account-link="redeem" href="#rc-treats">Redeem now</a>
  </div>
  <div class="nudge only-member" data-ll="nudge" style="display:none"><span class="nudge__icon">🎂</span>
    <div class="nudge__body"><div class="nudge__t" data-ll="nudgeText"></div>
    <div class="nudge__bar"><div class="nudge__fill" data-ll="nudgeFill" style="width:0%"></div></div></div></div>
  <div class="guest-cta only-guest"><a href="/account/register">Join or log in to start redeeming →</a></div>
  <h3 class="subhead">Vouchers</h3><div class="vgrid"><!--VOUCHERS--></div>
  <h3 class="subhead">Free cake slices</h3><div class="cards"><!--SLICES--></div>
  <button class="btn btn--ghost cards__more" type="button" data-more data-count="{len(slices)}">See all {len(slices)} flavours &rarr;</button>
</section>

<!--FLAVOUR_SLOT-->

<!-- TIERS MATRIX -->
<section class="section s-tiers">
  <div class="section__head"><span class="eyebrow">Your status</span><h2>Three tiers. The more you order, the more you earn.</h2>
    <p>You move up automatically as you spend — and every tier keeps everything below it, plus more.</p></div>
  <div class="mx-scroll">{matrix_html}</div>
  <p class="mx-rank only-member" data-ll="rank" style="display:none"></p>
  <p class="mx-note">Your tier is based on your total spend with Elevete. Climb higher, earn Crumbs faster, unlock more.</p>
</section>

<!-- EARN -->
<section class="section section--tint s-earn" id="rc-earn">
  <div class="section__head"><span class="eyebrow">Ways to earn</span><h2>Earn Crumbs</h2></div>
  <div class="quest only-member"><div class="quest__label" data-ll="quest"></div><div class="quest__bar"><div class="quest__fill" data-ll="questfill" style="width:0%"></div></div></div>
  <div class="earn-feat"><span class="earn-feat__icon">{purchase['icon']}</span>
    <div><div class="earn-feat__t">{esc(purchase['title'])}</div><div class="earn-feat__d">Your main way to earn — it adds up fast</div></div>
    <div class="earn-feat__pts"><span data-ll="earnrate">5–10</span><small>Crumbs per RM1</small></div></div>
  <div class="tiles"><!--TILES--></div>

  <!-- REFERRAL: the biggest single earn action (1,000 Crumbs) and historically 0 completions,
       because members had no way to actually get their link. Hidden until the SDK supplies one. -->
  <div class="refer only-member" data-ll="refer" style="display:none">
    <div class="refer__top"><span class="refer__icon">👯</span>
      <div><h3 class="refer__title">Give RM10, get a free cake slice</h3>
      <p class="refer__how">Share your link and your friend gets <b>RM10 off</b> their first order (min spend RM85).
      Once they've ordered RM75 or more, <b>1,000 Crumbs</b> land in your account — exactly a free cake slice.</p></div></div>
    <div class="refer__row">
      <input class="refer__link" data-ll="referLink" readonly onclick="this.select()" aria-label="Your referral link">
      <button class="btn btn--primary refer__copy" type="button">Copy link</button>
    </div>
    <a class="refer__wa" data-ll="referWa" target="_blank" rel="noopener">Share on WhatsApp</a>
    <p class="refer__fine">New customers only. Up to 10 referrals a month.</p>
  </div>
</section>

<!-- COMING SOON -->
<section class="section section--tint s-soon">
  <div class="section__head"><span class="eyebrow">In the pipeline</span><h2>More treats on the way</h2>
    <p>We're always cooking up new ways to reward you. Here's a taste of what's coming to Elevete Fam.</p></div>
  <div class="soon-grid">{coming_html}</div>
</section>

<!-- GRATITUDE -->
<section class="section s-thanks">
  <div class="thanks"><h2 class="thanks__t">Thank you for being part of Elevete</h2>
    <p class="thanks__p">Elevete Fam is our way of giving back to the people who keep choosing us. The more you enjoy, the more there is to look forward to — and this is only the beginning.</p></div>
</section>

<!-- FAQ -->
<section class="section s-faq">
  <div class="section__head"><span class="eyebrow">Good questions</span><h2>Everything you need to know</h2></div>
  <div class="faq">{faq_html}</div>
</section>

</div>
<div class="sticky only-member"><span class="sticky__txt">You have <b data-ll="points2">0</b> Crumbs to spend<span class="sticky__goal" data-ll="stickyGoal" style="display:none"></span></span><a class="btn btn--primary" data-lion-account-link="redeem" href="#rc-treats">Redeem</a></div>
<!-- Guests had NO persistent CTA: past the hero there was no way to join without scrolling back,
     even though the guest is the one we're trying to convert. Held back until the hero scrolls
     away (IntersectionObserver, not a scroll handler) so it never competes with the hero button. -->
<div class="sticky sticky--guest only-guest" data-guest-cta><span class="sticky__txt">Join free &mdash; your past orders <b>already count</b></span><a class="btn btn--primary" href="/account/register">Join</a></div>
</div>'''

# member/guest ordering: reuse prototype order via scoped CSS already present (is-member/is-guest)

JS = r'''
(function(){
  var root=document.currentScript.closest('.rc-club-mount')||document;
  var club=document.querySelector('.rc-club'); if(!club) return;
  var reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  club.classList.add('js');
  // Declared HERE, before anything reads it. It previously sat further down the script: `var`
  // hoisting made it `undefined` for the guest calculator below, which threw and — because the
  // throw was uncaught — halted the REST of the script including the LoyaltyLion rendering.
  var TIERS=<!--TIERS_LIQUID-->;
  revealSetup();   // runs for guests AND members — never gate content on the member path

  // --- Guest: "Where would you land?" tier calculator -------------------------------
  // Answers the hero's claim with the visitor's own number. No LoyaltyLion data needed,
  // so it works before they have an account. Input-driven only: nothing runs until touched.
  // try/catch on purpose: these are optional enhancements. An uncaught throw here would halt
  // the rest of the script and take the LoyaltyLion member rendering down with it — which is
  // exactly what happened when TIERS was read before it was declared.
  try{
  (function(){
    var rng=club.querySelector('[data-calc="range"]'); if(!rng) return;
    var set=function(k,v){ var e=club.querySelector('[data-calc="'+k+'"]'); if(e) e.innerHTML=v; };
    function update(){
      var spend=+rng.value;
      var ti = spend>=1000 ? 2 : (spend>=250 ? 1 : 0);
      var t=TIERS[ti], perSlice=Math.round(1000/t.rate);
      set('spend','RM'+spend.toLocaleString());
      set('tier',t.name);
      // Sells the forward EARN RATE, not lifetime-spend × rate. The old version multiplied their
      // years of spend by the rate ("that's 21,000 Crumbs, 21 free slices") — implying a signup
      // windfall that does NOT exist: past orders set the TIER, not the Crumbs balance. Same
      // retroactive-Crumbs over-promise we fixed in the member FAQ; kept consistent here.
      set('detail', spend===0
        ? 'Start at <b>Foodie</b> and climb as you order — everything counts from day one.'
        : (ti===2?'Our top tier. ':'')+'You&rsquo;d earn <b>'+t.rate+' Crumbs per RM1</b> going forward — '
          +'a free cake slice about every <b>RM'+perSlice.toLocaleString()+'</b> you spend.');
    }
    rng.addEventListener('input',update);
    update();
  })();

  // --- Guest sticky CTA: appear once the hero is out of view --------------------------
  // Observer rather than a scroll listener — fires twice, costs nothing while idle.
  (function(){
    var bar=club.querySelector('[data-guest-cta]'); if(!bar) return;
    var hero=club.querySelector('.s-ghero');
    if(!hero || !('IntersectionObserver' in window)){ bar.classList.add('is-on'); return; }
    new IntersectionObserver(function(es){
      es.forEach(function(e){ bar.classList.toggle('is-on', !e.isIntersecting); });
    },{threshold:0}).observe(hero);
  })();

  // --- Flavour of the Month: format the guest range, and adapt what it buys -----------
  // Liquid has no thousands separator, so "1200–2400" renders unformatted. Rebuild the line
  // here with grouped numbers. render() overwrites this with the member's own figure.
  (function(){
    var fe=club.querySelector('[data-ll="flavourEarn"]'); if(!fe) return;
    var lo=+fe.dataset.c0||0, hi=+fe.dataset.c2||0; if(!lo||!hi) return;
    var buys = lo>=1200 ? 'that&rsquo;s a free Premium cake slice'
             : (lo>=1000 ? 'that&rsquo;s a free cake slice'
             : 'worth RM'+(lo/100).toFixed(2).replace(/\.00$/,'')+'&ndash;RM'+(hi/100).toFixed(2).replace(/\.00$/,'')+' back');
    fe.innerHTML='Order it this month and earn <b>'+lo.toLocaleString()+'&ndash;'+hi.toLocaleString()+
                 ' Crumbs</b> on it, depending on your tier &mdash; '+buys+'.';
  })();

  }catch(e){ /* enhancement failed; core page and member rendering continue */ }

  // --- Pick your goal ----------------------------------------------------------------
  // Writes the reward id to localStorage and re-runs render(), so the card state, the nudge, its
  // progress bar and the sticky bar all update from one source instead of being patched by hand
  // in four places. Tapping the current goal clears it.
  (function(){
    var sec=club.querySelector('.s-treats'); if(!sec) return;
    sec.addEventListener('click',function(ev){
      var btn=ev.target.closest('[data-goal]'); if(!btn) return;
      ev.preventDefault(); ev.stopPropagation();          // never trigger redeem or the ringgit flip
      var cd=btn.closest('[data-rid]'); if(!cd) return;
      try{
        var cur=localStorage.getItem('rc_goal_v1');
        if(cur===cd.dataset.rid) localStorage.removeItem('rc_goal_v1');
        else localStorage.setItem('rc_goal_v1', cd.dataset.rid);
      }catch(e){ return; }                                 // private mode: leave the page untouched
      if(window.__rcRender) window.__rcRender();
    });
  })();

  // --- Locked reward -> a plan, in ringgit -------------------------------------------
  // "100 Crumbs to go" is a number; "About RM20 more" is something you can act on. Delegated, so
  // it survives the grid being reordered and the See-all toggle, and bound once at init rather
  // than per card. Values are computed in render() at the member's own earn rate; this only swaps
  // text, so a tap can never produce a wrong figure.
  (function(){
    var sec=club.querySelector('.s-treats'); if(!sec) return;
    function flip(el){
      if(!el.dataset.plan) return;
      var showing=el.classList.toggle('rc__go--plan');
      el.textContent = showing ? el.dataset.plan : el.dataset.crumbs;
    }
    sec.addEventListener('click',function(ev){
      var el=ev.target.closest('.rc__go--tap'); if(!el) return;
      ev.preventDefault(); ev.stopPropagation(); flip(el);
    });
    sec.addEventListener('keydown',function(ev){
      if(ev.key!=='Enter' && ev.key!==' ') return;
      var el=ev.target.closest && ev.target.closest('.rc__go--tap'); if(!el) return;
      ev.preventDefault(); flip(el);
    });
  })();

  // --- Reveal the rest of the flavours on demand (guest AND member) -------------------
  // Deliberately OUTSIDE the try above. It used to sit inside, which meant one throw in a guest
  // enhancement — as happened once with a hoisting bug — would silently take the toggle with it,
  // and a member would be stuck at six flavours with a dead button.
  (function(){
    var btn=club.querySelector('[data-more]'); if(!btn) return;
    btn.addEventListener('click',function(){
      var grid=club.querySelector('.cards'); if(!grid) return;
      var open=grid.classList.toggle('show-all');
      btn.innerHTML = open ? 'See less &uarr;' : 'See all '+(btn.dataset.count||'')+' flavours &rarr;';
      if(!open) grid.scrollIntoView({block:'start',behavior:reduce?'auto':'smooth'});
    });
  })();
  // Mirrors the "Referral share message" configured on the LoyaltyLion referral rule —
  // keep the two in sync so the wording is identical wherever a member shares from.
  var SHARE_MSG="I'm obsessed with Elevete's cakes 🍰 — here's RM10 off your first order:";
  var UNLOCK={1:'Exclusive flavour previews',2:'First dibs on limited editions'};

  function toGuest(){ club.classList.remove('is-member'); club.classList.add('is-guest'); }
  function q(s){ return club.querySelector(s); } function qa(s){ return club.querySelectorAll(s); }

  function render(c){
    club.classList.remove('is-guest'); club.classList.add('is-member');
    // Re-entry point for the goal picker: re-render from the SAME customer object so one tap
    // updates card state, nudge, progress bar and sticky bar together, with no page reload and
    // no second source of truth. Guarded so a re-render can never run before the first one.
    // Caught so one bad re-render can't kill the click handler, but NOT swallowed: a throw part
    // way through leaves the card half-updated (new title, stale eyebrow), which is invisible
    // without this line and very hard to diagnose from a screenshot.
    window.__rcRender=function(){ try{ render(c); }catch(e){ if(window.console) console.warn('[sweet-club] re-render failed:',e); } };
    var pts = (c.pointsRedeemable!=null?c.pointsRedeemable:(c.pointsApproved||0));
    qa('[data-ll="firstName"]').forEach(function(e){e.textContent=c.firstName||'there';});
    qa('[data-ll="points"],[data-ll="points2"]').forEach(function(e){e.dataset.target=pts;e.textContent=pts.toLocaleString();});
    // tier + progress
    // TIER RESOLUTION — deliberately paranoid, and here is why.
    // The Admin API returns the tier NESTED (`loyalty_tier_membership.loyalty_tier.id`), not as a
    // flat `loyalty_tier_id`. I assumed the flat path in a checker on 23 Jul and it reported a
    // fully-imported base as "NOT DONE" — a confident false negative. This code made the SAME
    // assumption about the client SDK. If the SDK is nested too, every member silently renders as
    // Foodie: wrong tier name, wrong earn rate, wrong unlock lines, wrong ringgit conversions,
    // wrong status line. Silent, because 28162 is a perfectly valid-looking answer.
    // So: try every plausible shape, then match on name, then infer from spend, and only then
    // fall back to Foodie.
    var tm=c.loyaltyTierMembership||c.loyalty_tier_membership||{};
    var tobj=tm.loyaltyTier||tm.loyalty_tier||c.loyaltyTier||c.loyalty_tier||{};
    var tid=tm.loyaltyTierId||tm.loyalty_tier_id||tobj.id||c.loyaltyTierId||0;
    if(!tid){
      var tname=(tobj.name||tm.name||c.loyaltyTierName||'').toString().toLowerCase();
      if(tname) for(var ti=0;ti<TIERS.length;ti++)
        if(TIERS[ti].name.toLowerCase()===tname){ tid=TIERS[ti].id; break; }
    }
    if(!tid){
      // Last resort: derive from eligible spend using the SAME thresholds LoyaltyLion uses, which
      // is far better than telling a Connoisseur they're in Foodie.
      var sp0=c.loyaltyTierEligibleSpend||0, best=TIERS[0];
      for(var tj=0;tj<TIERS.length;tj++) if(sp0>=(TIERS[tj].min||0)) best=TIERS[tj];
      tid=best.id;
    }
    var ci=Math.max(0,TIERS.findIndex(function(t){return t.id===tid;}));
    // 🔴 loyaltyTierEligibleSpend is in MINOR UNITS (cents). Verified 24 Jul against a live
    // Indulgent member: SDK returned 25000, which is RM250.00 — exactly the Indulgent floor.
    // Read as ringgit it became "RM25,000 spent", so the tracker filled to 100% and told an
    // Indulgent member "Spend RM0 more to reach Connoisseur". Every member would have been told
    // they were at the top tier.
    //
    // Detected rather than blindly divided, in case the unit ever changes, and then CLAMPED into
    // the band of the tier LoyaltyLion actually assigned. The tier is authoritative; the bar must
    // never contradict the tier name sitting next to it. This also absorbs the import artifact
    // where eligible spend is seeded at the tier floor instead of true lifetime spend.
    var spend=c.loyaltyTierEligibleSpend||0;
    var _band=TIERS[ci]||TIERS[0];
    var _ceil=_band.max||_band.min||1;
    if(spend > _ceil*10) spend=spend/100;                       // clearly minor units
    if(spend < (_band.min||0)) spend=_band.min||0;               // never below the tier's own floor
    if(_band.max && spend > _band.max) spend=_band.max;          // never above it either
    var tEl=q('[data-ll="tier"]'); if(tEl)tEl.textContent=TIERS[ci].name;
    // The featured earn rate was baked from the Foodie variant, so Indulgent and Connoisseur
    // members were shown "5 per RM1" when they actually earn 7 and 10 — contradicting the tier
    // matrix further down the page. Show THEIR rate. Guests keep the "5–10" range.
    var erEl=q('[data-ll="earnrate"]'); if(erEl)erEl.textContent=TIERS[ci].rate;
    // Flavour of the Month: swap the guest range for THIS member's actual number, and say what
    // it buys. Nobody should have to work out what "double Crumbs" means for their own tier.
    var fe=q('[data-ll="flavourEarn"]');
    if(fe){
      var fc=+fe.dataset['c'+ci]||0;
      if(fc>0){
        var buys = fc>=1200 ? 'a free Premium cake slice'
                 : (fc>=1000 ? 'a free cake slice'
                 : 'RM'+(fc/100).toFixed(2).replace(/\.00$/,'')+' off a future order');
        fe.innerHTML='Order it this month and earn <b>'+fc.toLocaleString()+' Crumbs</b> on it &mdash; that&rsquo;s '+buys+'.';
      }
    }
    // fill along 3-stop bar (0->250 = first 50%, 250->1000 = next 50%)
    var fillPct=0, goal='', unlock='';
    // The unlock line used to name one perk ("Unlocks Exclusive flavour previews"), which is the
    // vaguest thing the next tier offers. The concrete thing is the earn rate, so lead with it —
    // and state it as a comparison so nobody has to hold two numbers in their head.
    // NEAREST-WIN FRAMING. Goal-gradient only motivates when the goal feels CLOSE; a big remaining
    // number discourages. And loyaltyTierEligibleSpend can be seeded at the tier floor, so "RMx
    // more" may overstate the true remaining. So: show the precise nudge ONLY when they're within
    // ~RM200 of the boundary (genuinely close + plausibly-real); otherwise frame the next tier
    // qualitatively and let the unlock line carry the reason. The nearest *reward* (the worth line
    // above) is the real, accurate near-goal doing the motivating.
    if(ci<2){
      var nextNm=TIERS[ci+1].name, toNext;
      if(ci===0){ fillPct=Math.min(50, spend/250*50); toNext=Math.max(0,250-spend); }
      else      { fillPct=50+Math.min(50,(spend-250)/750*50); toNext=Math.max(0,1000-spend); }
      goal = (toNext>0 && toNext<=200)
        ? 'Just <b>RM'+toNext+'</b> more to reach '+nextNm
        : 'You&rsquo;re on your way to <b>'+nextNm+'</b>';
      unlock='🔓 '+nextNm+' earns <b>'+TIERS[ci+1].rate+' Crumbs per RM1</b> instead of '+TIERS[ci].rate+', plus '+UNLOCK[ci+1].toLowerCase();
    }
    // Top tier had a goal and then nothing — a dead end for our 1,609 best customers. Give the
    // line back to them by naming what they've got rather than what they're missing.
    else { fillPct=100; goal="You're at our top tier 🎉"; unlock='🏆 You earn <b>'+TIERS[2].rate+' Crumbs per RM1</b> — our best rate.'; }
    var g=q('[data-ll="goal"]'); if(g)g.innerHTML=goal;
    var u=q('[data-ll="unlock"]'); if(u)u.innerHTML=unlock;
    var f=q('[data-ll="fill"]'); if(f){ f.dataset.w=fillPct+'%'; if(reduce)f.style.width=fillPct+'%'; }
    // stops done state
    qa('.track__stop').forEach(function(s){ var si=+s.dataset.stop; s.classList.toggle('track__stop--done', si<=ci); });
    // matrix current tier highlight
    qa('.mx__head[data-tier],.mx__val[data-tier]').forEach(function(e){ e.classList.toggle('is-cur', +e.dataset.tier===ci); });
    // A CHOSEN GOAL OUTRANKS THE NEAREST REWARD. Without one the nudge points at whatever costs
    // least, which is rarely what the member actually wants. `rc_goal_v1` holds a reward id; if
    // that reward has since left the catalogue we fall back to nearest rather than showing
    // nothing. Everything below is driven by this single decision.
    // "a MYR 10 voucher" -> "RM10". The config uses a non-breaking space, so match on digits only.
    function vAmt(el){ var m=(el && el.dataset.name||'').match(/([\d.,]+)/); return m?'RM'+m[1]:''; }
    var goalCard=null;
    try{
      var gid=localStorage.getItem('rc_goal_v1');
      if(gid) goalCard=document.querySelector('.s-treats [data-rid="'+gid.replace(/"/g,'')+'"]');
    }catch(e){}
    qa('.card,.vcard').forEach(function(cd){
      var on = !!goalCard && cd===goalCard;
      cd.classList.toggle('is-goal', on);
      var gb=cd.querySelector('[data-goal]');
      if(gb){
        gb.setAttribute('aria-pressed', on?'true':'false');
        gb.querySelector('.goal__i').textContent = on?'★':'☆';
        gb.querySelector('.goal__t').textContent = on?'Your goal':'Set as my goal';
        gb.title = on?'This is your goal — tap to clear it':'Set as my goal';
      }
      var flag=cd.querySelector('.goal__flag');
      if(on && !flag){ var f=document.createElement('span'); f.className='goal__flag'; f.textContent='★ Your goal';
        (cd.querySelector('.card__img')||cd).appendChild(f); }
      else if(!on && flag){ flag.remove(); }
    });

    // affordability on reward cards
    var okc=0;
    qa('.card,.vcard').forEach(function(cd){ var cost=+cd.dataset.cost; var ok=pts>=cost;
      cd.classList.toggle('is-ok',ok); cd.classList.toggle('is-lock',!ok);
      var go=cd.querySelector('.rc__go');
      if(go){
        if(ok){
          go.textContent='Redeem'; go.classList.add('rc__go--ok');
          go.classList.remove('rc__go--tap','rc__go--plan'); go.removeAttribute('role'); go.removeAttribute('tabindex');
          okc++;
        } else {
          // Locked. Store the gap in BOTH currencies so the tap handler is pure display, and
          // convert at this member's own rate (5/7/10 per RM1) — an average would be wrong for
          // two thirds of the base. Rounded up so we never promise a treat a ringgit too early.
          var gap=cost-pts;
          go.dataset.crumbs=gap.toLocaleString()+' Crumbs to go';
          go.dataset.plan='About RM'+Math.ceil(gap/TIERS[ci].rate).toLocaleString()+' more';
          go.textContent=go.dataset.crumbs;
          go.classList.remove('rc__go--ok','rc__go--plan'); go.classList.add('rc__go--tap');
          go.setAttribute('role','button'); go.setAttribute('tabindex','0');
          go.setAttribute('aria-label',go.dataset.crumbs+' — tap to see it in ringgit');
          // A locked reward can't be redeemed, so don't let LoyaltyLion's redeem binding fire.
          go.removeAttribute('data-lion-account-link');
        }
      }
    });
    // CLAIMABLE FIRST. The catalogue is authored Premium-then-Standard, so a member holding 1,100
    // Crumbs met SEVEN locked Premium slices before reaching the eight Standard ones they could
    // actually claim — the exact deficit framing we stripped out of the copy, smuggled back in by
    // DOM order. Stable partition: the two halves keep their internal order, so Premium/Standard
    // grouping survives, and nothing moves at all when everything is affordable (Connoisseurs) or
    // nothing is (new members). Runs ~1,500px below the fold after the SDK resolves, so it can't
    // shift anything the member is looking at.
    // The chosen goal always leads, even when it's locked and everything else is claimable —
    // otherwise a goal sitting at position 12 would be hidden by the six-card collapse, and the
    // member would be tracking a reward they can't see.
    // Sorted from `data-ord` — the position the card was AUTHORED in — never from wherever the
    // DOM happens to sit now. The old version partitioned the current order in place, so once a
    // goal had moved a card to the front, clearing that goal left it there: unstarring the RM10
    // voucher did not put RM5 back in front. Sorting against a fixed origin makes every state
    // reachable from every other, in any order, forever.
    ['.s-treats .cards','.s-treats .vgrid'].forEach(function(sel){
      var grid=q(sel); if(!grid) return;
      var kids=[].slice.call(grid.children);
      kids.sort(function(a,b){
        var ag=a.classList.contains('is-goal')?0:1, bg=b.classList.contains('is-goal')?0:1;
        if(ag!==bg) return ag-bg;                                   // the goal always leads
        var ao=a.classList.contains('is-ok')?0:1, bo=b.classList.contains('is-ok')?0:1;
        if(ao!==bo) return ao-bo;                                   // then anything claimable
        return (+a.dataset.ord||0)-(+b.dataset.ord||0);             // then authored order
      });
      kids.forEach(function(k){ grid.appendChild(k); });
    });

    // A new member with a small balance would otherwise read "you can redeem 0 of these right now"
    // above a wall of locked rewards — a deficit framing at exactly the moment they need
    // encouragement. When nothing is affordable yet, point forward instead; the nudge directly
    // below already tells them precisely how close the first one is.
    var an=q('[data-ll="afford"]');
    if(an){
      an.innerHTML = okc>0
        ? 'With your <b>'+pts.toLocaleString()+' Crumbs</b> you can redeem <b>'+okc+'</b> of these right now.'
        : 'You&rsquo;re at <b>'+pts.toLocaleString()+' Crumbs</b> — here&rsquo;s what they&rsquo;re building toward.';
    }
    // "YOU'RE IN THE TOP N%" — status, not money. Percentiles are real: of 78,652 buyers with a
    // lifetime-spend tier, 1,609 are Connoisseur (2%) and 17,060 are Indulgent or above (22%).
    // Foodie members are the majority, so telling them their percentile would deflate rather than
    // motivate — they get the same number framed as the thing to aim at instead.
    var rk=q('[data-ll="rank"]');
    if(rk){
      rk.innerHTML = ci===2 ? '🏆 You&rsquo;re in the top <b>4%</b> of Elevete Fam members.'
                   : ci===1 ? 'You&rsquo;re in the top <b>22%</b> of Elevete Fam members.'
                   : 'Reach Indulgent and you&rsquo;d be in the top <b>22%</b> of Elevete Fam members.';
      rk.style.display='block';
    }

    // THE MEMBER SIMULATOR. Reads the real catalogue out of the DOM, so it can never promise a
    // reward that isn't on the page, and converts at this member's own rate rather than an average.
    (function(){
      var rng=q('[data-sim="range"]'); if(!rng) return;
      var sp=q('[data-sim="spend"]'), ea=q('[data-sim="earn"]'), de=q('[data-sim="detail"]');
      var costs=[].slice.call(document.querySelectorAll('.s-treats .card,.s-treats .vcard'))
        .map(function(c){ return {cost:+c.dataset.cost, name:c.dataset.name||'a treat',
             title:(c.querySelector('.card__title')||{}).textContent}; })
        .filter(function(x){ return x.cost>0; })
        .sort(function(a,b){ return a.cost-b.cost; });
      var sliceCosts=[].slice.call(document.querySelectorAll('.s-treats .card'))
        .map(function(c){ return +c.dataset.cost; }).filter(Boolean);
      var minSliceCost=sliceCosts.length?Math.min.apply(null,sliceCosts):0;
      function upd(){
        var add=+rng.value, rate=TIERS[ci].rate, earned=Math.round(add*rate), total=pts+earned;
        if(sp) sp.textContent='RM'+add.toLocaleString();
        if(add===0){
          if(ea) ea.innerHTML='Drag to see what an order would earn you.';
          if(de) de.innerHTML='';
          return;
        }
        if(ea) ea.innerHTML='You&rsquo;d earn <b>'+earned.toLocaleString()+' Crumbs</b>'
          +' &mdash; taking you to <b>'+total.toLocaleString()+'</b>';
        // Answer in CAKE, like the hero line does. Picking the single dearest affordable reward
        // meant every total above 1,500 answered "a MYR 15 voucher" — technically the most
        // expensive thing and the least exciting, and it made the slider look broken because the
        // answer stopped changing. Slices are also ~35% COGS against a voucher's 100%.
        var bits=[], next=null;
        costs.forEach(function(x){ if(x.cost>total && (!next || x.cost<next.cost)) next=x; });
        if(minSliceCost && total>=minSliceCost){
          var n=Math.floor(total/minSliceCost), rem=total-n*minSliceCost;
          bits.push('Enough for <b>'+(n===1?'a free cake slice':n.toLocaleString()+' free cake slices')+'</b>'
                    +(rem>=100?' with '+rem.toLocaleString()+' to spare':''));
        } else if(next){
          bits.push('<b>'+(next.cost-total).toLocaleString()+' Crumbs</b> short of '+next.name);
        }
        // Would this order also move them up a tier? The strongest reason to spend a little more.
        if(ci<2){
          var nextTier=TIERS[ci+1], after=spend+add;
          if(after>=nextTier.min) bits.push('and you&rsquo;d reach <b>'+nextTier.name+'</b>');
          else bits.push('RM'+(nextTier.min-after).toLocaleString()+' more after that reaches '+nextTier.name);
        }
        if(de) de.innerHTML=bits.join(' &middot; ')+'.';
      }
      if(!rng.dataset.bound){ rng.dataset.bound='1'; rng.addEventListener('input',upd); }
      upd();
    })();

    // WHAT THE BALANCE IS WORTH. "1,100" is a number the member has to do arithmetic on; "a free
    // cake slice, with 100 Crumbs to spare" is a reason to open the app. Read from the live cards
    // rather than baked constants, so this can never contradict the catalogue further down.
    // Deliberately cake-first even when a bigger voucher is affordable: a slice costs us ~35% of
    // face where cash costs 100%, and it's the better thing to receive.
    var wEl=q('[data-ll="worth"]');
    if(wEl){
      var sc=[].slice.call(document.querySelectorAll('.s-treats .card')).map(function(c){return +c.dataset.cost;}).filter(Boolean);
      var vc=[].slice.call(document.querySelectorAll('.s-treats .vcard'));
      var minSlice=sc.length?Math.min.apply(null,sc):0, bestV=null, cheapV=null;
      vc.forEach(function(v){ var c=+v.dataset.cost; if(!c) return;
        if(c<=pts && (!bestV||c>bestV.c)) bestV={c:c,n:v.dataset.name||''};
        if(!cheapV||c<cheapV.c) cheapV={c:c,n:v.dataset.name||''}; });
      var rm=function(o){ var m=o&&o.n.match(/([\d.,]+)/); return m?'RM'+m[1]:'money off'; };
      var cr=function(n){ return n.toLocaleString()+' Crumb'+(n===1?'':'s'); };
      var w='';
      if(minSlice && pts>=minSlice){
        var n=Math.floor(pts/minSlice), rem=pts-n*minSlice;
        w='That&rsquo;s <b>'+(n===1?'a free cake slice':n.toLocaleString()+' free cake slices')+'</b>'
          +(rem>=100?', with '+cr(rem)+' to spare':'')+'.';
      } else if(bestV){
        w='That&rsquo;s <b>'+rm(bestV)+' off</b> your next order &mdash; or '
          +(minSlice-pts).toLocaleString()+' more for a free cake slice.';
      } else if(cheapV){
        w='<b>'+cr(cheapV.c-pts)+' more</b> and you&rsquo;ve got '+rm(cheapV)+' off your next order.';
      }
      if(w){ wEl.innerHTML=w; wEl.style.display='block'; } else { wEl.style.display='none'; }
    }

    // CRUMBS EXPIRY — honest loss aversion, fires only when points are genuinely about to expire.
    // Shape of pointsExpiringNext is undocumented, so accept object {points,date} / number, and
    // fall back to pointsExpiryDate for the date. Threshold 60 days. Never fabricated: no real
    // expiry date within window => stays hidden (which is the case today, pre-Mar-2027).
    var xEl=q('[data-ll="expiry"]');
    if(xEl){
      var xAmt=0, xDate=null, pn=c.pointsExpiringNext;
      if(pn && typeof pn==='object'){ xAmt=pn.points||pn.amount||pn.value||0; xDate=pn.expiresAt||pn.expiryDate||pn.date||pn.expiry||c.pointsExpiryDate; }
      else if(typeof pn==='number'){ xAmt=pn; xDate=c.pointsExpiryDate; }
      var shown=false;
      if(xAmt>0 && xDate){
        var d=new Date(xDate), days=Math.ceil((d-new Date())/86400000);
        if(days>0 && days<=60){
          var rmv='RM'+(xAmt/100).toFixed(2).replace(/\.00$/,'');
          xEl.innerHTML='⏳ <b>'+xAmt.toLocaleString()+' Crumbs</b> ('+rmv+') expire on <b>'
            +d.toLocaleDateString('en-MY',{day:'numeric',month:'short'})+'</b> &mdash; a quick order keeps them.';
          xEl.style.display='block'; shown=true;
        }
      }
      if(!shown) xEl.style.display='none';
    }

    // "SINCE YOUR LAST VISIT" — the returning-member hook. Kept entirely in localStorage: no
    // backend, no LoyaltyLion call, nothing to break. Only ever shown when the balance has GONE
    // UP, so redeeming (a drop) never reads as a loss. Wrapped because storage throws in
    // private mode and this is decoration, not content.
    // The same record also carries the tier, so a CROSSING can be caught and celebrated — the
    // one genuinely rare event on this page. It outranks the "+X Crumbs" pill, so only one of
    // the two ever shows. Members stored before this shipped have no `tier`, so the first visit
    // after release records it silently and never fakes a promotion.
    try{
      var SEEN='rc_seen_v1';
      var prev=JSON.parse(localStorage.getItem(SEEN)||'null');
      var sEl=q('[data-ll="since"]'), tuEl=q('[data-ll="tierup"]');
      var tieredUp = !!(prev && typeof prev.tier==='number' && ci>prev.tier);
      if(tuEl && tieredUp){
        tuEl.innerHTML='🎉 You&rsquo;ve reached <b>'+TIERS[ci].name+'</b> — you now earn <b>'
          +TIERS[ci].rate+' Crumbs</b> on every RM1 you spend.';
        tuEl.style.display='block';
        if(!reduce) burst();
        // At the top tier the banner and the trophy line would both state the same rate. The
        // banner is the moment; the trophy line is the standing state, so it returns next visit.
        if(ci===2 && u) u.innerHTML='';
      }
      if(sEl && !tieredUp && prev && typeof prev.pts==='number' && pts>prev.pts){
        sEl.innerHTML='<b>+'+(pts-prev.pts).toLocaleString()+' Crumbs</b> since your last visit';
        sEl.style.display='inline-block';
      }
      localStorage.setItem(SEEN, JSON.stringify({pts:pts, tier:ci, t:Date.now()}));
    }catch(e){}

    // "YOUR BEST TREAT RIGHT NOW" — surfaces the highest-value reward they can already afford so
    // acting is one tap instead of scrolling 18 tiles. Hidden entirely when nothing is affordable.
    // Ranked by cost, but a TIE goes to the cake, not the voucher: a slice and the RM10 voucher
    // both cost 1,000, and product costs us ~35% of face where cash costs 100% — plus a free
    // cake is the better gift and the whole point of a product-led catalogue.
    // If a goal is set and affordable it IS the best treat — otherwise the card would advertise
    // one reward while the nudge and sticky bar advertise another, which is the exact opposite of
    // what picking a goal is for.
    var bestR=null;
    if(goalCard && (+goalCard.dataset.cost)<=pts){
      var gti=goalCard.querySelector('.card__title'), gim=goalCard.querySelector('img');
      bestR={cost:+goalCard.dataset.cost, isProduct:goalCard.classList.contains('card'),
             name:(gti && gti.textContent.trim()) ? 'a free '+gti.textContent.trim() : (goalCard.dataset.name||'your goal'),
             img:gim?gim.getAttribute('src'):'', amt:vAmt(goalCard), isGoal:true};
    }
    if(!bestR) qa('.card,.vcard').forEach(function(cd){
      var cost=+cd.dataset.cost; if(cost>pts) return;
      var isProduct=cd.classList.contains('card');
      if(!bestR || cost>bestR.cost || (cost===bestR.cost && isProduct && !bestR.isProduct)){
        var im=cd.querySelector('img'), ti=cd.querySelector('.card__title');
        // Name the actual flavour. The card carried this photo already, so labelling it with the
        // generic reward title ("a free Standard cake slice") put a picture of Black Forest under
        // a line that never said Black Forest. The specific name is both truer and more appetising.
        bestR={cost:cost, isProduct:isProduct,
               name:(isProduct && ti && ti.textContent.trim()) ? 'a free '+ti.textContent.trim() : (cd.dataset.name||'a treat'),
               img:im?im.getAttribute('src'):'', amt:vAmt(cd)};
      }
    });
    var bEl=q('[data-ll="best"]');
    if(bEl){
      if(bestR){
        var nm=bestR.name.charAt(0).toUpperCase()+bestR.name.slice(1);
        var bt=q('[data-ll="bestTitle"]'); if(bt) bt.textContent=nm;
        var be=q('.best__eyebrow'); if(be) be.textContent = bestR.isGoal ? '\u2605 Your goal is ready' : 'Ready for you';
        // Naming one flavour could read as "this is your only option", so when the pick is a
        // slice, point at the other 14 sitting right below it.
        var bn=q('[data-ll="bestNote"]');
        if(bn) bn.textContent = bestR.isGoal
          ? 'The goal you picked. Claim it whenever you like.'
          : bestR.isProduct
          ? 'You have enough Crumbs. Claim it, or pick another flavour below.'
          : 'You have enough Crumbs. Claim it whenever you like.';
        // Vouchers have no photograph, and an empty 72px hole next to "Your goal is ready" looks
        // like a broken image. Draw the voucher instead — same purple tile as its card downpage.
        var bi=q('[data-ll="bestImg"]');
        if(bi){
          bi.innerHTML = bestR.img
            ? '<img src="'+bestR.img+'" alt="" loading="lazy" width="200" height="200">'
            : '<span class="best__vouch">'+(bestR.amt||'RM')+'<em>off</em></span>';
          bi.classList.toggle('best__img--v', !bestR.img);
        }
        bEl.style.display='flex';
      } else { bEl.style.display='none'; }
    }

    // NEXT-REWARD NUDGE (the "you're almost there" hook — ZUS-style near-miss motivation).
    // Finds the CHEAPEST reward still out of reach and shows the gap + a progress bar.
    // Computed here rather than baked in Liquid because the balance is only known at runtime.
    var nx=null;
    if(goalCard){
      nx={cost:+goalCard.dataset.cost,
          name:(goalCard.querySelector('.card__title')||{}).textContent
               ? goalCard.querySelector('.card__title').textContent.trim()
               : (goalCard.dataset.name||'your goal'),
          isGoal:true};
    } else {
      qa('.card,.vcard').forEach(function(cd){ var cost=+cd.dataset.cost;
        if(cost>pts && (!nx || cost<nx.cost)) nx={cost:cost, name:cd.dataset.name||'your next reward'}; });
    }
    var nu=q('[data-ll="nudge"]'), nt=q('[data-ll="nudgeText"]'), nf=q('[data-ll="nudgeFill"]');
    if(nu){
      if(nx){
        var gap=nx.cost-pts, pct=Math.max(2,Math.min(100,Math.round(pts/nx.cost*100)));
        if(nx.isGoal && gap<=0){
          // The "Your goal is ready" card sits directly above this. Saying it twice in a row is
          // noise, so the nudge stands down and lets the card carry it.
          nu.style.display='none';
          nx=null;
        }
        if(nx){
          if(nt){
            nt.innerHTML = nx.isGoal
              ? ('Your goal: <b>'+nx.name+'</b> &mdash; '+gap.toLocaleString()
                 +' Crumbs to go, about RM'+Math.ceil(gap/TIERS[ci].rate).toLocaleString()+' more.')
              : ("You're just <b>"+gap.toLocaleString()+" Crumbs</b> from "+nx.name);
          }
          if(nf){ nf.dataset.w=pct+'%'; if(reduce) nf.style.width=pct+'%'; }
          nu.style.display='flex';
        }
      } else { nu.style.display='none'; }  // can already afford everything, and no goal set
    }
    // The sticky bar becomes goal-aware too, so the target follows the member down the page.
    var sg=q('[data-ll="stickyGoal"]');
    if(sg){
      if(goalCard && (+goalCard.dataset.cost)>pts){
        sg.textContent=' · '+((+goalCard.dataset.cost)-pts).toLocaleString()+' from your goal';
        sg.style.display='inline';
      } else { sg.style.display='none'; }
    }
    // earn quest (completed rules)
    var done={}; (c.completedRules||[]).forEach(function(r){ done[r.kind||r]=true; });
    var oneTime=['join_program','newsletter_signup','instagram_follow','facebook_like','tiktok_follow'];
    var dc=0;
    // Tile states. "Claim →" was a FALSE AFFORDANCE — these tiles are plain divs with no click
    // handler, and LoyaltyLion credits these actions through its own widget, so a link here would
    // send someone off to follow us and award them nothing. Wording is now honest: done, or not yet.
    // Automatic rules (join bonus, birthday) can't be claimed at all, so they describe themselves.
    var AUTO_TEXT={join_program:'Added when you join',birthday:'Lands on your birthday'};
    var claimable=0, claimed=0;
    qa('.tile[data-kind]').forEach(function(t){ var k=t.dataset.kind; var st=t.querySelector('.tile__state'); if(!st)return;
      // The referral tile is only-guest (members get the dedicated block instead). Counting it
      // gave members "2 of 6 claimed" where the 6th was invisible and unreachable from this page.
      // Never count a tile the member cannot see.
      if(t.classList.contains('only-guest')) return;
      var isDone=!!done[k];
      if(t.dataset.auto==='1'){
        // "Added when you join" is guest copy. The member reading it has already joined, so state
        // it as the fact it is — the tile text itself stays future-tense for guests.
        st.textContent = (k==='join_program') ? '✓ Added when you joined' : (AUTO_TEXT[k]||'Automatic');
        st.className='tile__state only-member tile__state--auto';
        if(isDone) t.classList.add('is-done');
        return;                                   // never counted as a claimable quest step
      }
      claimable++;
      if(isDone){ claimed++; st.textContent='✓ Claimed'; st.className='tile__state only-member tile__state--done'; t.classList.add('is-done'); if(oneTime.indexOf(k)>=0)dc++; }
      else { st.textContent='Not yet claimed'; st.className='tile__state only-member tile__state--todo'; }
    });
    var ql=q('[data-ll="quest"]');
    // "0 of 5 claimed" reads as five things you've failed to do. At zero, frame it as what's
    // available; at full, acknowledge it. The middle case is genuinely progress, so it stays.
    if(ql){
      ql.innerHTML = claimed===0
        ? 'Bonus Crumbs — <b>'+claimable+' waiting</b> for you'
        : (claimed>=claimable
            ? 'Bonus Crumbs — <b>all claimed</b>, nice work'
            : 'Bonus Crumbs — <b>'+claimed+' of '+claimable+'</b> claimed');
    }
    var qf=q('[data-ll="questfill"]'); if(qf){var pct=Math.round(claimed/Math.max(1,claimable)*100); qf.dataset.w=pct+'%'; if(reduce)qf.style.width=pct+'%';}

    // REFERRAL LINK. The SDK's referralUrls shape is not documented and could not be verified
    // against live data (programme was wiped/offline), so accept every plausible form and simply
    // stay hidden if none yields a URL — better an absent block than a broken one.
    var ru=c.referralUrls, link='';
    if(typeof ru==='string'){ link=ru; }
    else if(ru && typeof ru==='object'){
      link = ru.url || ru.direct || ru.link || ru.share || '';
      if(!link){ for(var k in ru){ if(typeof ru[k]==='string' && ru[k].indexOf('http')===0){ link=ru[k]; break; } } }
    }
    if(!link && c.referralUrl) link=c.referralUrl;
    var rb=q('[data-ll="refer"]'), ri=q('[data-ll="referLink"]'), rw=q('[data-ll="referWa"]');
    if(rb && link){
      if(ri) ri.value=link;
      if(rw) rw.href='https://wa.me/?text='+encodeURIComponent(SHARE_MSG+' '+link);
      rb.style.display='block';
      var cp=rb.querySelector('.refer__copy');
      if(cp && !cp.dataset.bound){
        cp.dataset.bound='1';
        cp.addEventListener('click',function(){
          var ok=function(){ cp.textContent='Copied ✓'; setTimeout(function(){cp.textContent='Copy link';},2000); };
          if(navigator.clipboard && navigator.clipboard.writeText){ navigator.clipboard.writeText(link).then(ok,ok); }
          else { try{ ri.select(); document.execCommand('copy'); ok(); }catch(e){} }
        });
      }
    }

    if(!reduce) animate();
  }

  function animate(){
    // count-up
    qa('[data-ll="points"],[data-ll="points2"]').forEach(function(el){
      var target=+el.dataset.target||0,s=null;
      function up(ts){if(!s)s=ts;var p=Math.min((ts-s)/900,1);el.textContent=Math.round(target*(1-Math.pow(1-p,3))).toLocaleString();if(p<1)requestAnimationFrame(up);}
      requestAnimationFrame(up);
    });
    // fill bars on view
    var fills=qa('.track__fill,.quest__fill,.nudge__fill');
    var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){var f=e.target;f.style.transition='width 1s cubic-bezier(.23,1,.32,1)';f.style.width=f.dataset.w||'0';io.unobserve(f);}});},{threshold:.4});
    fills.forEach(function(f){io.observe(f);});
  }

  // Reveal/visibility setup. MUST run for EVERYONE, not just members: the tier-matrix ticks
  // are hidden by CSS until .mx gets .in, so when this lived inside render() (member-only,
  // and skipped entirely under reduced-motion) every logged-out guest saw a comparison matrix
  // with no ticks at all — the perk ladder invisible to the exact audience it's meant to sell.
  function revealSetup(){
    var rev=qa('.card,.tile,.vcard,.soon,.step');
    var mx=q('.mx');
    function showAll(){ if(mx) mx.classList.add('in'); rev.forEach(function(el){ el.classList.add('in'); }); }
    if(reduce){ showAll(); return; }              // reduced motion: show immediately, no animation
    rev.forEach(function(el){el.classList.add('reveal');});
    var io2=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io2.unobserve(e.target);}});},{threshold:.12});
    rev.forEach(function(el){io2.observe(el);});
    if(mx){var io3=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io3.unobserve(e.target);}});},{threshold:.25});io3.observe(mx);}
    // SAFETY NET: content must never depend on an animation firing. If an observer never
    // fires (element taller than the viewport so the threshold is never met, background tab,
    // headless/bot render, a JS error elsewhere), force everything visible anyway.
    setTimeout(showAll,2500);
    // confetti on redeem tap
    document.addEventListener('click',function(ev){ if(ev.target.closest('.rc__go--ok,.btn--primary')) burst(); });
  }
  function burst(){ var c=document.getElementById('rc-confetti'); if(!c){c=document.createElement('canvas');c.id='rc-confetti';document.body.appendChild(c);}
    var x=c.getContext('2d');c.width=innerWidth;c.height=innerHeight;var cols=['#E8622A','#4A2D8F','#FCD34D','#fff'],p=[];
    for(var i=0;i<90;i++)p.push({x:innerWidth/2,y:innerHeight*0.38,vx:(Math.random()-0.5)*13,vy:Math.random()*-13-3,col:cols[i%4],s:Math.random()*6+4,r:Math.random()*6,vr:(Math.random()-0.5)*0.5});
    var s=null;function fr(ts){if(!s)s=ts;var e=ts-s;x.clearRect(0,0,c.width,c.height);p.forEach(function(o){o.vy+=0.42;o.x+=o.vx;o.y+=o.vy;o.r+=o.vr;x.save();x.translate(o.x,o.y);x.rotate(o.r);x.fillStyle=o.col;x.fillRect(-o.s/2,-o.s/2,o.s,o.s);x.restore();});if(e<1300)requestAnimationFrame(fr);else x.clearRect(0,0,c.width,c.height);}
    requestAnimationFrame(fr);
  }

  // wait for LoyaltyLion SDK + customer (loads via GTM, async); default to guest
  // ---- Wait for LoyaltyLion, then render ------------------------------------
  // The SDK boots in stages (loader.js -> start/<token>.js -> authenticate customer),
  // so window.loyaltylion.customer can appear well after DOM ready. Polling alone was
  // giving up too early and leaving a logged-in member staring at a hollow shell
  // (name from Shopify, but 0 Crumbs / blank tier goal). So: hook the SDK's own
  // 'ready' event (the loader buffers `on` calls made before the SDK lands) AND keep
  // a longer poll as a belt-and-braces fallback.
  var done=false, start=Date.now();
  function tryRender(){
    if(done) return true;
    var ll=window.loyaltylion;
    if(ll && ll.customer && ll.customer.enrolled){ done=true; render(ll.customer); return true; }
    return false;
  }
  try{
    if(window.loyaltylion && typeof window.loyaltylion.on==='function'){
      window.loyaltylion.on('ready', function(){ if(!tryRender()) giveUp(); });
    }
  }catch(e){}
  function giveUp(){
    if(done) return; done=true;
    if(club.dataset.shopifyCustomer!=='1'){ toGuest(); return; }
    // Logged into Shopify but LoyaltyLion never answered. Don't fake a 0 balance and
    // don't show "join now" to an existing member — say plainly that it didn't load.
    var b=q('[data-ll="points"]'); if(b) b.textContent='—';
    var g=q('[data-ll="goal"]');
    if(g) g.innerHTML='We couldn’t load your Crumbs just now — please refresh.';
  }
  (function poll(){
    if(tryRender()) return;
    if(Date.now()-start>25000){ giveUp(); return; }
    setTimeout(poll,400);
  })();
})();
'''

# --- Flavour of the Month (self-serve: team controls it via the "double-crumbs" collection) ---
FLAVOUR_SECTION = r'''{%- if section.settings.fw_enabled -%}
{%- assign fw = collections['double-crumbs'] -%}
{%- if fw != blank and fw.products.size > 0 -%}
{%- assign fp = fw.products.first -%}
{%- comment -%}
  "Double Crumbs" means nothing to someone who doesn't know their own earn rate, and asking a
  customer to multiply price x rate x 2 is exactly the maths we don't want them doing. So compute
  the actual Crumbs for each tier here (price is in cents; rates are 5/7/10, doubled = 10/14/20)
  and hand them the finished number. Guests see the range, members see their own via JS.
{%- endcomment -%}
{%- assign fp_rm = fp.price | divided_by: 100.0 -%}
{%- assign c_sweets = fp_rm | times: 10 | round -%}
{%- assign c_indulgent = fp_rm | times: 14 | round -%}
{%- assign c_conn = fp_rm | times: 20 | round -%}
<section class="section section--tint s-flavour">
  <div class="section__head"><span class="eyebrow">{{ section.settings.fw_eyebrow | default: 'This month only' }}</span><h2>{{ section.settings.fw_heading | default: 'Flavour of the Month' }}</h2>
    {%- if section.settings.fw_subtext != blank %}<p>{{ section.settings.fw_subtext }}</p>{% endif -%}</div>
  <a class="flavour" href="{{ fp.url }}">
    <div class="flavour__img">
      {%- if fp.featured_image -%}<img src="{{ fp.featured_image | image_url: width: 800 }}" alt="{{ fp.title | escape }}" width="800" height="800" loading="lazy">{%- endif -%}
      <span class="flavour__badge">2&times; Crumbs</span>
    </div>
    <div class="flavour__body">
      <h3 class="flavour__title">{{ fp.title | escape }}</h3>
      <p class="flavour__earn" data-ll="flavourEarn"
         data-c0="{{ c_sweets }}" data-c1="{{ c_indulgent }}" data-c2="{{ c_conn }}">
        Order it this month and earn <b>{{ c_sweets }}&ndash;{{ c_conn }} Crumbs</b> on it, depending on your tier &mdash; that&rsquo;s a free cake slice.
      </p>
      <span class="flavour__cta">Shop this month&rsquo;s flavour &rarr;</span>
    </div>
  </a>
</section>
{%- endif -%}
{%- endif -%}'''

FLAVOUR_CSS = '''
.rc-club .flavour{display:flex;flex-direction:column;background:#fff;overflow:hidden;text-decoration:none;color:inherit;max-width:600px;margin:0 auto;border:1.5px solid var(--orange);border-radius:14px}
.rc-club .flavour__img{position:relative;aspect-ratio:16/10;overflow:hidden;background:var(--cream-2)}
.rc-club .flavour__img img{width:100%;height:100%;object-fit:cover;display:block}
.rc-club .flavour__badge{position:absolute;top:12px;left:12px;background:var(--orange);color:#fff;font-family:var(--display);font-size:13px;letter-spacing:.02em;padding:6px 12px;border-radius:999px}
.rc-club .flavour__body{padding:18px 20px}
.rc-club .flavour__title{font-family:var(--display);font-size:21px;color:var(--purple);margin-bottom:6px}
.rc-club .flavour__note{font-size:14px;color:var(--ink-soft);margin-bottom:12px}
.rc-club .flavour__earn{font-size:15px;color:var(--ink-soft);line-height:1.5;margin-bottom:12px}
.rc-club .flavour__earn b{color:var(--orange);font-family:var(--display);font-size:17px}
.rc-club .flavour__cta{font-weight:700;color:var(--orange)}
@media(min-width:820px){.rc-club .flavour{flex-direction:row;max-width:760px} .rc-club .flavour__img{flex:0 0 46%;aspect-ratio:auto;min-height:240px} .rc-club .flavour__body{display:flex;flex-direction:column;justify-content:center;flex:1}}
'''
MARKUP = MARKUP.replace('<!--FLAVOUR_SLOT-->', FLAVOUR_SECTION)

# --- Structure: full-bleed sections, one .wrap INSIDE each ---------------------
# The prototype nests <section class="section--tint"> > <div class="wrap">, so the tint
# runs edge-to-edge and .wrap only constrains the CONTENT. This port originally put a
# single .wrap AROUND all the sections, which trapped every tinted section inside the
# 1120px container — the tint then painted as a floating box with hard vertical seams
# on the cream page instead of a full-width band. Restore the prototype's nesting.
MARKUP = MARKUP.replace('<div class="rc-club is-guest">\n<div class="wrap">',
                        '<div class="rc-club is-guest">', 1)
MARKUP = MARKUP.replace('</div>\n<div class="sticky only-member">',
                        '\n<div class="sticky only-member">', 1)
assert '<div class="wrap">' not in MARKUP, "outer .wrap was not removed — check MARKUP head/tail"
_n_sections = len(re.findall(r'<section\b', MARKUP))
MARKUP = re.sub(r'(<section\b[^>]*>)(.*?)(</section>)',
                r'\1<div class="wrap">\2</div>\3', MARKUP, flags=re.S)
assert MARKUP.count('<div class="wrap">') == _n_sections, "wrap-per-section transform mismatch"
print("sections given their own .wrap:", _n_sections)

# --- Customer-aware rendering (CRITICAL: also defeats Shopify's full-page cache) -----
# Shopify only marks a page `cache-control: private, no-store` if its Liquid references
# `customer`. This section originally got everything from the LoyaltyLion JS and never
# touched `customer`, so /pages/rewards was publicly cacheable — logged-in customers were
# served a CACHED logged-out copy (logged-out header, LL init with no customer), and the
# member view could never activate. Referencing customer here fixes that AND renders the
# member/guest state server-side, so there's no guest flash while the SDK boots.
# NOTE: must run AFTER the wrap restructure above, which matches on the original
# `<div class="rc-club is-guest">` string.
MARKUP = MARKUP.replace(
    '<div class="rc-club is-guest">',
    '<div class="rc-club {% if customer %}is-member{% else %}is-guest{% endif %}"'
    ' data-shopify-customer="{% if customer %}1{% else %}0{% endif %}">', 1)
MARKUP = MARKUP.replace(
    '<span data-ll="firstName">there</span>',
    "<span data-ll=\"firstName\">{{ customer.first_name | default: 'there' | escape }}</span>")
assert '{% if customer %}' in MARKUP, "customer reference missing — page would stay cacheable"

# ---------------------------------------------------------------------------------------------
# LIVE CATALOGUE. The reward grids render from a PAGE METAFIELD that `sync_config.py` keeps in
# step with LoyaltyLion, so adding, re-pricing or removing a reward shows up on the very next page
# load — no rebuild, no theme push. The LoyaltyLion key never touches the browser: the sync runs
# server-side and Shopify serves the result.
#
# The baked HTML stays as the {% else %} branch and is the floor, never the ceiling: if the
# metafield is missing, empty or malformed, the page renders exactly what it does today rather
# than an empty shelf. A live catalogue must not become a new way for the page to break.
GOAL_BTN=('<button class="goal only-member" type="button" data-goal aria-pressed="false"'
          ' title="Set as my goal"><span class="goal__i" aria-hidden="true">☆</span>'
          '<span class="goal__t">Set as my goal</span></button>')

VOUCHERS_LIQUID = (
 "{%- assign rc_cat = page.metafields.sweet_club.catalogue.value -%}\n"
 "{%- if rc_cat.vouchers.size > 0 -%}{%- for v in rc_cat.vouchers -%}\n"
 '<div class="vcard" data-rid="{{ v.id }}" data-ord="{{ forloop.index0 }}" data-cost="{{ v.pts }}"'
 ' data-name="a {{ v.amt | escape }} voucher">\n'
 '  <span class="vcard__amt">{{ v.amt | escape }}</span><span class="vcard__sub">off your order</span>\n'
 '  <span class="vcard__pts">{{ v.pts }} Crumbs</span>\n'
 '  <span class="rc__go only-member" data-lion-account-link="redeem"></span>' + GOAL_BTN + '</div>\n'
 "{%- endfor -%}{%- else -%}\n" + vouchers_html + "\n{%- endif -%}")

SLICES_LIQUID = (
 "{%- if rc_cat.slices.size > 0 -%}{%- for s in rc_cat.slices -%}\n"
 '<div class="card" data-rid="{{ s.id }}" data-ord="{{ forloop.index0 }}" data-cost="{{ s.pts }}"'
 ' data-name="a free {{ s.tier | escape }} cake slice">\n'
 '  <div class="card__img">{%- if s.img != blank -%}<img src="{{ s.img }}" alt="{{ s.title | escape }}"'
 ' loading="lazy" width="400" height="400">{%- else -%}<div class="ph"></div>{%- endif -%}'
 '<span class="card__tier card__tier--{{ s.tier | downcase }}">{{ s.tier }}</span>'
 '<span class="card__lock only-member">\U0001F512 Locked</span></div>\n'
 '  <div class="card__body"><h4 class="card__title">{{ s.title | escape }}</h4>\n'
 '  <span class="card__pts">{{ s.pts }} Crumbs</span>\n'
 '  <span class="rc__go only-member" data-lion-account-link="redeem"></span>' + GOAL_BTN + '</div></div>\n'
 "{%- endfor -%}{%- else -%}\n" + slices_html + "\n{%- endif -%}")

# TIERS from the metafield when it's there, baked array when it isn't. This one line makes the
# earn rates and tier thresholds live everywhere they're used: unlock lines, the ringgit figure on
# locked rewards, the simulator, the "what it's worth" line, the tracker and the matrix highlight.
_baked_tiers = json.dumps([
    {'id': t.get('id'), 'name': t.get('name'),
     'min': (t.get('lower_bound') or {}).get('amount') or 0,
     'max': (t.get('upper_bound') or {}).get('amount'),
     'rate': _rate_by_tier.get(t.get('id')) or 0}
    for t in sorted((cfg.get('tier_configuration') or {}).get('tiers', []),
                    key=lambda x: x.get('position') or 0)], separators=(',', ':'))
TIERS_LIQUID = ("{%- assign rc_cat = page.metafields.sweet_club.catalogue.value -%}"
                "{%- if rc_cat.tiers.size > 0 -%}{{ rc_cat.tiers | json }}"
                "{%- else -%}" + _baked_tiers + "{%- endif -%}")


# Earn tiles from the metafield too — the referral one stays guest-only because members get the
# dedicated block with their own link.
TILES_LIQUID = (
 "{%- if rc_cat.earn.size > 0 -%}"
 "{%- if rc_cat.referral -%}"
 '<div class="tile only-guest" data-kind="referral"><span class="tile__icon">{{ rc_cat.referral.icon }}</span>'
 '<span class="tile__label">{{ rc_cat.referral.title | escape }}</span>'
 '<span class="tile__pts">{{ rc_cat.referral.text | escape }}</span>'
 '<span class="tile__state only-member"></span></div>'
 "{%- endif -%}"
 "{%- for t in rc_cat.earn -%}"
 '<div class="tile" data-kind="{{ t.kind }}"{% if t.auto == 1 %} data-auto="1"{% endif %}>'
 '<span class="tile__icon">{{ t.icon }}</span>'
 '<span class="tile__label">{{ t.title | escape }}</span>'
 '<span class="tile__pts">{{ t.text | escape }}</span>'
 '<span class="tile__state only-member"></span></div>'
 "{%- endfor -%}{%- else -%}" + other_tiles + "{%- endif -%}")
MARKUP = MARKUP.replace('<!--TILES-->', TILES_LIQUID, 1)
assert '<!--TILES-->' not in MARKUP, "tiles placeholder not replaced"

MARKUP = MARKUP.replace('<!--VOUCHERS-->', VOUCHERS_LIQUID, 1)
MARKUP = MARKUP.replace('<!--SLICES-->', SLICES_LIQUID, 1)
for _ph in ('<!--VOUCHERS-->','<!--SLICES-->'):
    assert _ph not in MARKUP, "live-catalogue placeholder %s not replaced" % _ph
# The "See all N flavours" count must follow the LIVE list, not the baked one.
MARKUP = MARKUP.replace('>See all %d flavours &rarr;<' % len(slices),
                        '>See all {{ rc_cat.slices.size | default: %d }} flavours &rarr;<' % len(slices), 1)
MARKUP = MARKUP.replace('data-count="%d"' % len(slices),
                        'data-count="{{ rc_cat.slices.size | default: %d }}"' % len(slices), 1)

# Only ship the hero photo the visitor will actually SEE. `display:none` on the wrapper section
# does NOT stop Chrome fetching an <img> inside it, so leaving both in the DOM meant every guest
# downloading the member hero as well — two images competing at fetchpriority="high" on the guest's
# critical path. Liquid-gating them means one image each, and the guest hero's measured LCP stands.
MARKUP = MARKUP.replace('<img class="mhero__bg"', '{%- if customer -%}<img class="mhero__bg"', 1)
MARKUP = MARKUP.replace('<!--/mhero-img-->', '{%- endif -%}', 1)
MARKUP = MARKUP.replace('<img class="ghero__bg"', '{%- unless customer -%}<img class="ghero__bg"', 1)
MARKUP = MARKUP.replace('<!--/ghero-img-->', '{%- endunless -%}', 1)
for _m in ('/mhero-img','/ghero-img'):
    assert _m not in MARKUP, f"hero image gate failed for {_m} — guests would fetch both heroes"
assert 'customer.first_name' in MARKUP, "first name not wired to the Shopify customer"
scoped_css = scoped_css + '\n' + FLAVOUR_CSS

LIQUID = '{%- comment -%} Elevete — Elevete Fam rewards page. Custom section, wired to window.loyaltylion.customer (B-lite). {%- endcomment -%}\n'
# --- VISIBILITY GATE (soft launch) -------------------------------------------------
# The page is not public yet. Rather than relying only on the page's template suffix,
# the section itself refuses to render anywhere except the allow-listed page handles.
# This is belt-and-braces: even if Shopify resolves the rewards template on /pages/rewards
# (stale render, template cache, someone re-assigning it in admin), nothing is emitted.
# TO GO PUBLIC: add 'rewards' to rc_allowed_handles below, rebuild, push.
LIQUID += "{%- assign rc_allowed_handles = 'rewards,sweet-club-preview' | split: ',' -%}\n"
LIQUID += "{%- if rc_allowed_handles contains page.handle -%}\n"
LIQUID += '<style>\n'+scoped_css+'\n</style>\n'
LIQUID += MARKUP + '\n'
LIQUID += '<script>'+JS+'</script>\n'
LIQUID += "{%- endif -%}\n"
LIQUID += '''{% schema %}
{
  "name": "Elevete Fam Rewards",
  "tag": "section",
  "class": "section-rewards-club",
  "settings": [
    { "type": "header", "content": "Flavour of the Month" },
    { "type": "paragraph", "content": "Shows the first product in the 'double-crumbs' collection. To change the featured flavour, swap the product in that collection (Products > Collections > Double Crumbs). Also point your LoyaltyLion collection-bonus rule at the same collection so the points match." },
    { "type": "checkbox", "id": "fw_enabled", "label": "Show Flavour of the Month", "default": true },
    { "type": "text", "id": "fw_eyebrow", "label": "Eyebrow", "default": "This month only" },
    { "type": "text", "id": "fw_heading", "label": "Heading", "default": "Flavour of the Month" },
    { "type": "textarea", "id": "fw_subtext", "label": "Sub-text", "default": "Every month we put one treat in the spotlight. Order it before the month is out and it earns you double the Crumbs it normally would." }
  ],
  "presets": [{ "name": "Elevete Fam Rewards" }]
}
{% endschema %}
'''

LIQUID = LIQUID.replace('<!--TIERS_LIQUID-->', TIERS_LIQUID, 1)
assert '<!--TIERS_LIQUID-->' not in LIQUID, "TIERS placeholder not replaced"
# ⚠️  RETIRED — DO NOT WRITE THE LIVE SECTION FROM HERE (6 Aug 2026)
# sections/rewards-club.liquid in the theme repo is now HAND-MAINTAINED. It carries the member
# account hub, membership card, flavour passport, milestones, the challenge tracker and the
# accessibility fixes, none of which exist in this generator — and its JavaScript now lives in
# assets/rewards-club.js because the inline version breached Shopify's 256KB section limit.
# Regenerating would delete all of that AND re-break the size limit.
#
# This write was also MODULE-LEVEL with no __main__ guard, so it ran on every import — including
# the 5-minute cron, which imports this module for render_ready(). Now guarded.
#
# What this repo still does, and must keep doing: cloud_sync.py publishes the LoyaltyLion config
# to the Shopify metafield page.metafields.sweet_club.catalogue every 5 minutes. The section
# reads its rewards, slices, vouchers, tiers, earn rules and referral offer from that metafield,
# so LoyaltyLion changes reach the page within 5 minutes with no code change. That path is
# untouched by this guard.
#
# Full workflow: Shopify Editor Elevete/REWARDS-PAGE.md
if __name__ == '__main__' and os.environ.get('ALLOW_LEGACY_SECTION_BUILD') == '1':
    open('rewards-club.liquid','w').write(LIQUID)
elif __name__ == '__main__':
    raise SystemExit(
        'build_section.py no longer generates the live section.\n'
        'The section is hand-maintained at sections/rewards-club.liquid in the theme repo.\n'
        'See REWARDS-PAGE.md. To write the legacy file anyway (it will NOT be deployed):\n'
        '  ALLOW_LEGACY_SECTION_BUILD=1 python3 build_section.py')
print("section built:", len(LIQUID), "chars | vouchers", len(vouchers), "slices", len(slices))

# ---- local preview: mock the LL SDK (member + guest) for verification ----
def preview(member=True):
    # The section is now Liquid-driven in places (TIERS, the reward grids, the earn tiles). A file://
    # preview has no Liquid engine, so those tags ship raw and `var TIERS={%- assign ...` is a syntax
    # error that kills the whole member render. Resolve each conditional to its BAKED fallback —
    # exactly what a storefront with no metafield would see — so the preview stays a faithful,
    # testable copy of the worst-case path.
    mock = ""
    if member:
        mock = '''<script>window.loyaltylion={customer:{enrolled:true,firstName:"Aisyah",pointsApproved:1100,pointsRedeemable:1100,
          loyaltyTierMembership:{loyaltyTierId:28162},loyaltyTierEligibleSpend:180,completedRules:[{kind:"join_program"},{kind:"newsletter_signup"},{kind:"instagram_follow"}]}};</script>'''
    page='<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    page+='<link href="https://fonts.googleapis.com/css2?family=Dela+Gothic+One&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700&display=swap" rel="stylesheet">'
    import re as _re
    body = LIQUID.split('{% schema %}')[0]
    # {%- if X -%}A{%- else -%}B{%- endif -%}  ->  B   (the baked branch)
    for _ in range(6):
        new = _re.sub(r'\{%-?\s*if [^%]*?-?%\}.*?\{%-?\s*else\s*-?%\}(.*?)\{%-?\s*endif\s*-?%\}',
                      lambda m: m.group(1), body, flags=_re.S)
        if new == body: break
        body = new
    body = _re.sub(r'\{%-?.*?-?%\}', '', body, flags=_re.S)      # leftover tags
    body = _re.sub(r'\{\{.*?\}\}', '', body, flags=_re.S)        # leftover outputs
    page+='</head><body>'+mock+body.replace('{%- comment -%} Elevete — Elevete Fam rewards page. Custom section, wired to window.loyaltylion.customer (B-lite). {%- endcomment -%}','')+'</body></html>'
    fn='preview_'+('member' if member else 'guest')+'.html'
    open(fn,'w').write(page); return fn

print("previews:", preview(True), preview(False))
