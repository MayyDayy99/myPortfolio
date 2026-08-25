#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blog építése a blog/_posts/*.json fájlokból.

Futtatás a repó gyökeréből:   python3 scripts/build_blog.py

Egy poszt bemenete egy JSON fájl a blog/_posts/ mappában. Kötelező a title
és a content, minden más elhagyható. A tartalomposztoló ide ír fájlt, a
GitHub Action pedig lefuttatja ezt a szkriptet és commitolja az eredményt.

  { "title": "...", "date": "2026-08-25", "excerpt": "...",
    "content": "Markdown vagy HTML", "tags": ["..."], "cover": "images/x.jpg" }
"""
import re, json, os, glob, html, datetime, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')
POSTS = os.path.join(ROOT, 'blog', '_posts')
OUT = os.path.join(ROOT, 'blog')
SITE = 'https://portfolio.maydayprod.app'
AUTHOR = 'Nemes Péter'

HU_MAP = str.maketrans('áéíóöőúüűÁÉÍÓÖŐÚÜŰ', 'aeiooouuuAEIOOOUUU')


def slugify(t):
    t = t.translate(HU_MAP)
    t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode()
    t = re.sub(r'[^a-zA-Z0-9]+', '-', t).strip('-').lower()
    return t[:70] or 'poszt'


def md(text):
    """Nagyon kis markdown: címsor, félkövér, dőlt, link, lista, kód, bekezdés.
       Ha a bemenet már HTML-nek látszik, változatlanul hagyjuk."""
    if re.search(r'<(p|h[1-6]|ul|ol|div|section|article)\b', text, re.I):
        return text
    out, buf, lst = [], [], False

    def flush():
        if buf:
            out.append('<p>' + ' '.join(buf) + '</p>')
            buf.clear()

    def close_list():
        nonlocal lst
        if lst:
            out.append('</ul>'); lst = False

    for raw in text.split('\n'):
        line = raw.rstrip()
        if not line.strip():
            flush(); close_list(); continue
        hm = re.match(r'^(#{1,4})\s+(.*)$', line)
        if hm:
            flush(); close_list()
            lvl = min(4, len(hm.group(1)) + 1)      # a h1 az oldal címe marad
            out.append('<h%d>%s</h%d>' % (lvl, inline(hm.group(2)), lvl)); continue
        if re.match(r'^\s*[-*]\s+', line):
            flush()
            if not lst:
                out.append('<ul>'); lst = True
            out.append('<li>%s</li>' % inline(re.sub(r'^\s*[-*]\s+', '', line))); continue
        close_list()
        buf.append(inline(line))
    flush(); close_list()
    return '\n'.join(out)


def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', t)
    t = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', t)
    t = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)',
               r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
    return t


def chrome():
    """A fő oldal stílusa és fejléc-váza, hogy a blog egy az egyben ugyanúgy nézzen ki."""
    s = open(SRC, encoding='utf-8').read()
    style = re.search(r'<style>(.*?)</style>', s, re.S).group(1)
    fonts = '\n'.join(re.findall(r'<link[^>]*fonts\.(?:googleapis|gstatic)[^>]*>', s))
    return style, fonts


BLOG_CSS = """
.bl-wrap{max-width:var(--maxw-narrow);margin:0 auto;padding:0 var(--sp-5)}
.bl-head{padding-block:clamp(40px,7vw,80px) clamp(20px,3vw,34px)}
.bl-list{display:flex;flex-direction:column;gap:var(--gap-list);padding-bottom:clamp(56px,8vw,104px)}
.bl-card{display:block;border:1px solid var(--paper-3);border-radius:var(--r-md);background:#fff;padding:var(--pad-card);color:var(--text);transition:transform .2s var(--ease),box-shadow .2s var(--ease),border-color .2s}
.bl-card:hover{transform:translateY(-2px);box-shadow:var(--e-2);border-color:var(--ink-line)}
.bl-meta{font-family:"Space Mono",monospace;font-size:var(--fs-2xs);letter-spacing:var(--track-label);text-transform:uppercase;color:var(--amber-text);margin-bottom:9px}
.bl-card h2{font-size:var(--fs-lg);margin:0 0 8px;letter-spacing:-.01em}
.bl-card p{color:var(--muted);font-size:var(--fs-sm);margin:0}
.bl-tags{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}
.bl-tags span{font-family:"Space Mono",monospace;font-size:var(--fs-2xs);color:var(--muted);border:1px solid var(--paper-3);border-radius:var(--r-sm);padding:4px 9px}
.bl-empty{border:1px dashed var(--paper-3);border-radius:var(--r-md);padding:var(--sp-6);text-align:center;color:var(--muted)}
.bl-article{padding-bottom:clamp(56px,8vw,104px)}
.bl-article h1{font-size:var(--fs-xl);letter-spacing:-.02em;margin:0 0 14px}
.bl-cover{width:100%;border-radius:var(--r-md);border:1px solid var(--paper-3);margin:clamp(20px,3vw,30px) 0;display:block}
.bl-body{font-size:var(--fs-md);line-height:1.7;color:var(--text)}
.bl-body p{margin:0 0 1.05em}
.bl-body h2{font-size:var(--fs-lg);margin:1.8em 0 .5em;letter-spacing:-.01em}
.bl-body h3{font-size:var(--fs-md);margin:1.5em 0 .4em}
.bl-body ul{margin:0 0 1.05em;padding-left:1.2em}
.bl-body li{margin-bottom:.4em}
.bl-body a{color:var(--amber-text);text-decoration:underline;text-underline-offset:3px}
.bl-body code{font-family:"Space Mono",monospace;font-size:.9em;background:var(--paper-2);border-radius:4px;padding:2px 6px}
.bl-back{display:inline-flex;align-items:center;gap:8px;font-family:"Space Mono",monospace;font-size:var(--fs-xs);letter-spacing:var(--track-mono);color:var(--muted);margin-bottom:22px}
.bl-back:hover{color:var(--amber-text)}
.bl-foot{border-top:1px solid var(--paper-3);margin-top:clamp(36px,5vw,54px);padding-top:24px;display:flex;flex-wrap:wrap;gap:14px;align-items:center;justify-content:space-between}
"""


def page(style, fonts, title, desc, canonical, body, jsonld=''):
    return f"""<!doctype html>
<html lang="hu">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<meta name="theme-color" content="#eff1ec">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Nemes Péter · AI-fejlesztő">
<meta property="og:locale" content="hu_HU">
<meta property="og:url" content="{canonical}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="{SITE}/images/og.jpg">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%2312231f'/%3E%3Ctext x='33' y='43' font-family='monospace' font-size='29' font-weight='700' letter-spacing='1' fill='%23e2a23b' text-anchor='middle'%3EAI%3C/text%3E%3C/svg%3E">
{fonts}
<style>{style}{BLOG_CSS}</style>
{jsonld}
</head>
<body>
<header class="header">
  <div class="wrap nav">
    <a class="brand" href="/"><span class="dot"></span>Nemes Péter</a>
    <div class="nav-right">
      <div class="head-contact">
        <a href="/">Főoldal</a>
        <a href="/#munkak">Munkáim</a>
        <a href="/#kapcsolat">Kapcsolat</a>
        <a class="hc-phone" href="tel:+36205493710" aria-label="Telefon: +36 20 549 3710"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2 4.2 2 2 0 0 1 4 2h3a2 2 0 0 1 2 1.7c.1.9.3 1.8.6 2.6a2 2 0 0 1-.5 2.1L8 9.6a16 16 0 0 0 6 6l1.2-1.1a2 2 0 0 1 2.1-.5c.8.3 1.7.5 2.6.6a2 2 0 0 1 1.7 2z"/></svg><span class="hc-txt">+36 20 549 3710</span></a>
      </div>
    </div>
  </div>
</header>
{body}
<footer class="footer">
  <div class="wrap">
    <div class="footer-grid">
      <a href="/" class="brand">Nemes Péter</a>
      <nav class="footer-nav"><a href="/">Főoldal</a><a href="/blog/">Blog</a><a href="/#kapcsolat">Elérhetőség</a></nav>
    </div>
    <div class="footer-small">© <span id="year"></span> Nemes Péter · AI-fejlesztés &amp; oktatás</div>
  </div>
</footer>
<script>document.getElementById('year').textContent=new Date().getFullYear();</script>
</body>
</html>
"""


def load():
    posts = []
    for f in sorted(glob.glob(os.path.join(POSTS, '*.json'))):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception as e:
            print('  ! hibás JSON, kihagyva:', os.path.basename(f), e); continue
        if d.get('draft') is True or str(d.get('status') or '').lower() in ('draft', 'piszkozat', 'pending'):
            print('  - piszkozat, kihagyva:', os.path.basename(f)); continue
        title = d.get('title') or d.get('cim') or ''
        content = d.get('content') or d.get('body') or d.get('tartalom') or ''
        # a WordPress {"raw": ...} / {"rendered": ...} alakot is elfogadjuk
        if isinstance(title, dict): title = title.get('raw') or title.get('rendered') or ''
        if isinstance(content, dict): content = content.get('raw') or content.get('rendered') or ''
        title = str(title).strip()
        if not title or not content:
            print('  ! title vagy content hiányzik, kihagyva:', os.path.basename(f)); continue
        date = str(d.get('date') or d.get('datum') or '')[:10]
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
            date = datetime.date.fromtimestamp(os.path.getmtime(f)).isoformat()
        slug = d.get('slug') or slugify(title)
        excerpt = (d.get('excerpt') or d.get('leiras') or '').strip()
        if not excerpt:
            # csak az elso bekezdes, hogy a felsorolas ne folyjon egybe a mondattal
            first = re.search(r'<p>(.*?)</p>', md(content), re.S)
            plain = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                           first.group(1) if first else md(content))).strip()
            excerpt = plain[:180] + ('…' if len(plain) > 180 else '')
        tags = d.get('tags') or d.get('cimkek') or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',') if t.strip()]
        posts.append({'title': title, 'slug': slug, 'date': date, 'excerpt': excerpt,
                      'content': content, 'tags': tags, 'cover': d.get('cover') or d.get('kep') or '',
                      'file': os.path.basename(f)})
    posts.sort(key=lambda p: (p['date'], p['title']), reverse=True)
    return posts


def main():
    os.makedirs(POSTS, exist_ok=True)
    style, fonts = chrome()
    posts = load()
    print('posztok:', len(posts))

    # ── egyedi poszt-oldalak ──
    for p in posts:
        d = os.path.join(OUT, p['slug'])
        os.makedirs(d, exist_ok=True)
        url = f"{SITE}/blog/{p['slug']}/"
        ld = json.dumps({"@context": "https://schema.org", "@type": "BlogPosting",
                         "headline": p['title'], "datePublished": p['date'],
                         "dateModified": p['date'], "description": p['excerpt'],
                         "inLanguage": "hu", "mainEntityOfPage": url,
                         "author": {"@type": "Person", "name": AUTHOR,
                                    "@id": SITE + "/#person", "url": SITE + "/"},
                         "publisher": {"@id": SITE + "/#person"},
                         "image": (SITE + '/' + p['cover'].lstrip('/')) if p['cover'] else SITE + "/images/og.jpg",
                         "keywords": ", ".join(p['tags'])}, ensure_ascii=False, separators=(',', ':'))
        cover = f'<img class="bl-cover" src="/{p["cover"].lstrip("/")}" alt="" loading="lazy">' if p['cover'] else ''
        tags = ''.join(f'<span>{html.escape(t)}</span>' for t in p['tags'])
        body = f"""<main class="section">
  <div class="bl-wrap bl-article">
    <a class="bl-back" href="/blog/">← Vissza a bloghoz</a>
    <div class="bl-meta">{p['date']}</div>
    <h1>{html.escape(p['title'])}</h1>
    {cover}
    <div class="bl-body">{md(p['content'])}</div>
    {f'<div class="bl-tags">{tags}</div>' if tags else ''}
    <div class="bl-foot">
      <span class="bl-meta" style="margin:0">Nemes Péter · AI-fejlesztő</span>
      <a class="btn btn-amber btn--sm" href="/#kapcsolat">Kérj ajánlatot</a>
    </div>
  </div>
</main>"""
        open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(
            page(style, fonts, f"{p['title']} · Nemes Péter", p['excerpt'], url, body,
                 f'<script type="application/ld+json">{ld}</script>'))
        print('  →', f"blog/{p['slug']}/")

    # ── listaoldal ──
    if posts:
        items = '\n'.join(
            f"""      <a class="bl-card" href="/blog/{p['slug']}/">
        <div class="bl-meta">{p['date']}</div>
        <h2>{html.escape(p['title'])}</h2>
        <p>{html.escape(p['excerpt'])}</p>
        {f'<div class="bl-tags">{"".join(f"<span>{html.escape(t)}</span>" for t in p["tags"])}</div>' if p['tags'] else ''}
      </a>""" for p in posts)
    else:
        items = ('      <div class="bl-empty">Még nincs bejegyzés. '
                 'Az első poszt megjelenésekor automatikusan ide kerül.</div>')
    lld = json.dumps({"@context": "https://schema.org", "@type": "Blog",
                      "name": "Nemes Péter blogja", "url": SITE + "/blog/", "inLanguage": "hu",
                      "author": {"@id": SITE + "/#person"},
                      "blogPost": [{"@type": "BlogPosting", "headline": p['title'],
                                    "datePublished": p['date'],
                                    "url": f"{SITE}/blog/{p['slug']}/"} for p in posts[:20]]},
                     ensure_ascii=False, separators=(',', ':'))
    body = f"""<main class="section">
  <div class="bl-wrap bl-head">
    <span class="label label--accent">Blog</span>
    <h1>Amit közben tanulok</h1>
    <p class="lead">Rövid írások lokális AI-ról, automatizálásról és arról, mi működik a gyakorlatban kisvállalkozásoknál.</p>
  </div>
  <div class="bl-wrap">
    <div class="bl-list">
{items}
    </div>
  </div>
</main>"""
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(
        page(style, fonts, 'Blog · Nemes Péter', 
             'Rövid írások lokális AI-ról, automatizálásról és arról, mi működik a gyakorlatban kisvállalkozásoknál.',
             SITE + '/blog/', body, f'<script type="application/ld+json">{lld}</script>'))
    print('  → blog/index.html')

    # ── sitemap kiegészítése ──
    sm_path = os.path.join(ROOT, 'sitemap.xml')
    if os.path.exists(sm_path):
        sm = open(sm_path, encoding='utf-8').read()
        sm = re.sub(r'\n?  <url>\s*<loc>[^<]*/blog/[^<]*</loc>.*?</url>', '', sm, flags=re.S)
        add = ['  <url>', f'    <loc>{SITE}/blog/</loc>',
               f'    <lastmod>{posts[0]["date"] if posts else datetime.date.today().isoformat()}</lastmod>',
               '    <priority>0.7</priority>', '  </url>']
        for p in posts:
            add += ['  <url>', f'    <loc>{SITE}/blog/{p["slug"]}/</loc>',
                    f'    <lastmod>{p["date"]}</lastmod>', '    <priority>0.6</priority>', '  </url>']
        sm = sm.replace('</urlset>', '\n'.join(add) + '\n</urlset>')
        open(sm_path, 'w', encoding='utf-8').write(sm)
        print('  → sitemap.xml frissítve (%d blog-URL)' % (len(posts) + 1))


if __name__ == '__main__':
    main()
