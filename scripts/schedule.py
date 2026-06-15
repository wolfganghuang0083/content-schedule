# -*- coding: utf-8 -*-
"""
Content-map scheduling engine (brand-agnostic):
  read the content-map Google Sheet -> score importance -> plan/apply CMS schedule (future) -> write back to the map.

See SKILL.md. Credentials:
  - Google OAuth token JSON (spreadsheets scope) — default ~/.config/google/token.json, override with --token / GOOGLE_TOKEN.
  - CMS auth via env vars WP_USER / WP_APP_PW (never hardcode).
Needs google-api-python-client (run with a python that has googleapiclient).

CMS = WordPress REST as the reference implementation; to use another CMS, swap the `wp()` calls.
"""
import argparse, json, re, base64, os, urllib.request, urllib.error, datetime

# ============================ CONFIG (edit / override) ============================
# These defaults can all be overridden by CLI args or env vars (see argparse below).
TOKEN  = os.path.expanduser(os.environ.get('GOOGLE_TOKEN', '~/.config/google/token.json'))
SID    = os.environ.get('CONTENT_MAP_SHEET_ID', '')          # the content-map Google Sheet id
TAB    = os.environ.get('CONTENT_MAP_TAB', 'Content Map')    # worksheet/tab name
WPBASE = os.environ.get('CMS_BASE_URL', '')                  # e.g. https://your-site.com/wp-json
SITE   = os.environ.get('SITE_URL', '')                      # e.g. https://your-site.com (for admin edit links)
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36'

# Column index map (0-based) — MUST match your content map's columns.
# Defaults follow the content-map-builder template layout. Adjust if your sheet differs.
COL = {'cluster': 0, 'kw': 1, 'role': 2, 'status': 3, 'link': 4,
       'funnel': 16, 'conv': 17, 'imp': 19, 'clk': 20, 'sched': 22, 'edit': 23}
# Spreadsheet column LETTERS for the cells we write back (must line up with COL above):
COL_LETTER = {'status': 'D', 'sched': 'W', 'edit': 'X'}

# Importance scoring — tweak weights / keyword lists for your market & language.
ROLE_WEIGHTS    = [(('核心', 'core'), 35), (('藍海', 'blue', 'blue-ocean'), 28),
                   (('側翼', 'flank'), 22), (('長尾', 'support', 'long-tail'), 12)]
ROLE_DEFAULT    = 15
FUNNEL_WEIGHTS  = [(('BOFU', '轉換', '決策', 'bottom', 'conversion', 'decision'), 25),
                   (('MOFU', '評估', '比較', 'middle', 'evaluation', 'comparison'), 18),
                   (('TOFU', '認知', 'top', 'awareness'), 8)]
FUNNEL_DEFAULT  = 10
DECISION_KW     = ['vs', '比較', '費用', '價格', '挑選', '怎麼選', '怎麼挑', '避雷', '推薦',
                   'compare', 'price', 'cost', 'best', 'review', 'how to choose']
DECISION_BONUS  = 10
TIMELY_KW       = ['AI', '缺工', '自動化', 'AEO', 'Agent', 'automation']
TIMELY_BONUS    = 6
STATUS_ONLINE     = ['已上線', '✅', 'published', 'live']     # do NOT schedule these
STATUS_SCHEDULABLE = ['草稿', '審核通過', '🟡', 'draft', 'ready', 'approved']  # candidates to schedule
STATUS_SCHEDULED  = '🟢 scheduled'                           # marker written back on success
# =================================================================================


def sheets():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    d = json.load(open(TOKEN))
    c = Credentials(token=d.get('token'), refresh_token=d.get('refresh_token'), token_uri=d['token_uri'],
                    client_id=d['client_id'], client_secret=d['client_secret'], scopes=d.get('scopes'))
    if not c.valid:
        c.refresh(Request())
    return build('sheets', 'v4', credentials=c)


def get(row, key):
    i = COL[key]
    return row[i] if i < len(row) else ''


def _hit(text, kws):
    t = (text or '').lower()
    return any(k.lower() in t for k in kws)


def score(row):
    role = get(row, 'role') + get(row, 'cluster')
    funnel = get(row, 'funnel')
    kw = get(row, 'kw')
    s = 0
    for kws, w in ROLE_WEIGHTS:
        if _hit(role, kws):
            s += w; break
    else:
        s += ROLE_DEFAULT
    for kws, w in FUNNEL_WEIGHTS:
        if _hit(funnel, kws):
            s += w; break
    else:
        s += FUNNEL_DEFAULT
    imp = int(re.sub(r'[^0-9]', '', get(row, 'imp')) or 0)
    clk = int(re.sub(r'[^0-9]', '', get(row, 'clk')) or 0)
    s += min(20, imp // 80)
    if imp >= 200 and (clk / imp if imp else 1) < 0.02:
        s += 10                                   # high-impression low-CTR = quick win
    if get(row, 'conv').strip():
        s += 6
    if _hit(kw, DECISION_KW):
        s += DECISION_BONUS
    if _hit(kw, TIMELY_KW):
        s += TIMELY_BONUS
    return max(0, min(100, s))


def tier(s):
    return 'P0' if s >= 70 else 'P1' if s >= 55 else 'P2' if s >= 40 else 'P3'


def post_id(row):
    nums = [int(n) for n in re.findall(r'\d{3,6}', get(row, 'link'))]
    nums = [n for n in nums if not (2015 <= n <= 2035)]   # filter out year-like numbers
    return max(nums) if nums else None


def schedulable(row):
    st = get(row, 'status')
    if _hit(st, STATUS_ONLINE):
        return False
    return _hit(st, STATUS_SCHEDULABLE)


def parse_dt(s):
    s = (s or '').strip()
    for f in ('%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def wp(method, path, payload=None):
    user, pw = os.environ.get('WP_USER'), os.environ.get('WP_APP_PW')
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(WPBASE + path, data=data, method=method)
    req.add_header('User-Agent', UA)
    if user and pw:
        req.add_header('Authorization', 'Basic ' + base64.b64encode(f'{user}:{pw}'.encode()).decode())
    if payload is not None:
        req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def wp_future_dates():
    try:
        ps = wp('GET', '/wp/v2/posts?status=future&per_page=100&_fields=id,date')
        return [parse_dt(p['date']) for p in ps]
    except Exception as e:
        print('  (warn) failed to read CMS future posts:', e)
        return []


def edit_link(pid):
    return f'{SITE}/wp-admin/post.php?post={pid}&action=edit' if SITE else str(pid)


def gen_slots(start, per_day, skip_weekends, occupied, need):
    hours = [9] if per_day <= 1 else ([9, 15] if per_day == 2 else list(range(9, 9 + per_day)))
    occ = set((dt.year, dt.month, dt.day, dt.hour) for dt in occupied if dt)
    slots, d, guard = [], start, 0
    while len(slots) < need and guard < 500:
        guard += 1
        if not (skip_weekends and d.weekday() >= 5):
            for h in hours:
                dt = d.replace(hour=h, minute=0, second=0, microsecond=0)
                k = (dt.year, dt.month, dt.day, dt.hour)
                if k not in occ:
                    slots.append(dt); occ.add(k)
                    if len(slots) >= need:
                        break
        d = d + datetime.timedelta(days=1)
    return slots


def write_cells(svc, rownum, status=None, sched=None, edit=None):
    data = []
    if status is not None:
        data.append({'range': f"'{TAB}'!{COL_LETTER['status']}{rownum}", 'values': [[status]]})
    if sched is not None:
        data.append({'range': f"'{TAB}'!{COL_LETTER['sched']}{rownum}", 'values': [[sched]]})
    if edit is not None:
        data.append({'range': f"'{TAB}'!{COL_LETTER['edit']}{rownum}", 'values': [[edit]]})
    if data:
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=SID, body={'valueInputOption': 'RAW', 'data': data}).execute()


def main():
    global TOKEN, SID, TAB, WPBASE, SITE
    ap = argparse.ArgumentParser(description='Score content-map rows and schedule them to CMS (future).')
    ap.add_argument('--list', action='store_true', help='show rows with scores, write nothing')
    ap.add_argument('--plan', action='store_true', help='plan the calendar, write nothing')
    ap.add_argument('--apply', action='store_true', help='execute: set CMS future + write back to map')
    ap.add_argument('--post', type=int, default=0, help='single post id to schedule (with --date)')
    ap.add_argument('--date', default='', help='ISO datetime for --post, e.g. 2026-06-13T09:00:00')
    ap.add_argument('--start', default='', help='first scheduling day (YYYY-MM-DD)')
    ap.add_argument('--per-day', type=int, default=1)
    ap.add_argument('--skip-weekends', action='store_true')
    ap.add_argument('--sheet-id', default=SID, help='content-map Google Sheet id')
    ap.add_argument('--tab', default=TAB, help='worksheet/tab name')
    ap.add_argument('--base', default=WPBASE, help='CMS REST root, e.g. https://site/wp-json')
    ap.add_argument('--site', default=SITE, help='public site root for admin edit links')
    ap.add_argument('--token', default=TOKEN, help='Google OAuth token json path')
    a = ap.parse_args()
    TOKEN, SID, TAB, WPBASE, SITE = a.token, a.sheet_id, a.tab, a.base, a.site
    if not SID:
        print('ERROR: provide --sheet-id (or env CONTENT_MAP_SHEET_ID).'); return

    svc = sheets()
    rows = svc.spreadsheets().values().get(spreadsheetId=SID, range=f"'{TAB}'!A2:X").execute().get('values', [])

    # single post jump-the-queue
    if a.post and a.date:
        if not WPBASE:
            print('ERROR: --base required to write CMS.'); return
        r = wp('POST', f'/wp/v2/posts/{a.post}', {'status': 'future', 'date': a.date})
        print(f'CMS {a.post} -> future {r.get("date")} status={r.get("status")}')
        for idx, row in enumerate(rows):
            if post_id(row) == a.post:
                write_cells(svc, idx + 2, status=STATUS_SCHEDULED,
                            sched=a.date.replace('T', ' ')[:16], edit=edit_link(a.post))
                print(f'map row {idx + 2} updated -> {STATUS_SCHEDULED} / {a.date}')
                break
        return

    scored = []
    for idx, row in enumerate(rows):
        if not get(row, 'kw').strip():
            continue
        scored.append((idx, row, score(row)))

    if a.list:
        print('row | score P | role | status | post | sched | keyword')
        for idx, row, s in sorted(scored, key=lambda x: -x[2]):
            print(f'{idx+2:>3} | {s:>3} {tier(s)} | {get(row,"role")[:6]:<6} | {get(row,"status")[:10]:<10} | '
                  f'{post_id(row) or "-":<6} | {get(row,"sched")[:16]:<16} | {get(row,"kw")[:30]}')
        return

    todo = [(idx, row, s) for idx, row, s in scored
            if schedulable(row) and not get(row, 'sched').strip() and post_id(row)]
    todo.sort(key=lambda x: -x[2])
    occupied = [parse_dt(get(row, 'sched')) for _, row, _ in scored if get(row, 'sched').strip()]
    if WPBASE:
        occupied += wp_future_dates()
    start = parse_dt(a.start) if a.start else datetime.datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
    slots = gen_slots(start, a.per_day, a.skip_weekends, occupied, len(todo))

    print(f'to schedule: {len(todo)} | cadence {a.per_day}/day | start {start.date()}\n')
    plan = []
    for (idx, row, s), slot in zip(todo, slots):
        plan.append((idx, row, s, slot))
        print(f'  {slot.strftime("%m/%d %H:%M")} | {s:>3} {tier(s)} | id {post_id(row)} | {get(row,"kw")[:34]}')
    if len(todo) > len(slots):
        print(f'  (+{len(todo)-len(slots)} more await cadence extension)')

    if a.apply:
        if not WPBASE:
            print('ERROR: --base required to write CMS.'); return
        print('\n=== applying ===')
        for idx, row, s, slot in plan:
            pid = post_id(row)
            iso = slot.strftime('%Y-%m-%dT%H:%M:%S')
            try:
                r = wp('POST', f'/wp/v2/posts/{pid}', {'status': 'future', 'date': iso})
                write_cells(svc, idx + 2, status=STATUS_SCHEDULED,
                            sched=slot.strftime('%Y-%m-%d %H:%M'), edit=edit_link(pid))
                print(f'  OK id {pid} -> {r.get("status")} {r.get("date")} (map row {idx+2} updated)')
            except Exception as e:
                print(f'  FAIL id {pid}: {e}')
    elif a.plan:
        print('\n(--plan only plans; add --apply to write CMS + map)')


if __name__ == '__main__':
    main()
