#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Statikus nyelvi aloldalak és strukturált adat építése az index.html-ből.

Futtatás a repó gyökeréből:      python3 scripts/build_pages.py

Mit csinál:
  1. az index.html-be beteszi a magyar JSON-LD-t és a hreflang-sort
  2. legyártja az /en/ /es/ /zh/ /de/ /fr/ aloldalakat beégetett fordítással,
     hogy a keresők és az AI-crawlerek JavaScript nélkül is olvassák őket
  3. megírja a robots.txt, sitemap.xml és llms.txt fájlokat

A forrás mindig az index.html. Ha ott szöveget módosítasz, futtasd le újra.
"""
import re, json, os, datetime, html as htmllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')
SITE = 'https://portfolio.maydayprod.app'
LANGS = ['hu', 'en', 'es', 'zh', 'de', 'fr']
GEN = ['en', 'es', 'zh', 'de', 'fr']
LOCALE = {'hu': 'hu_HU', 'en': 'en_US', 'es': 'es_ES', 'zh': 'zh_CN', 'de': 'de_DE', 'fr': 'fr_FR'}
PATH = {'hu': '/', 'en': '/en/', 'es': '/es/', 'zh': '/zh/', 'de': '/de/', 'fr': '/fr/'}

JOB = {'hu': 'AI-fejlesztő', 'en': 'AI developer', 'es': 'Desarrollador de IA',
       'zh': 'AI 开发者', 'de': 'KI-Entwickler', 'fr': 'Développeur IA'}
REMOTE = {'hu': 'Távmunka világszerte', 'en': 'Remote worldwide', 'es': 'Remoto en todo el mundo',
          'zh': '全球远程', 'de': 'Remote weltweit', 'fr': 'À distance dans le monde entier'}
CATALOG = {'hu': 'Szolgáltatások', 'en': 'Services', 'es': 'Servicios',
           'zh': '服务', 'de': 'Leistungen', 'fr': 'Services'}
KNOWS = ['Local AI', 'Private AI', 'Large language models', 'Model Context Protocol',
         'Whisper', 'Stable Diffusion', 'ComfyUI', 'n8n', 'Retrieval augmented generation',
         'Autodesk Revit', 'Blender', 'Unity', 'Three.js', 'React', 'PyTorch', 'CUDA',
         'Web development', 'Web application development', 'Computer vision']


# ─────────────────────────── segédek ───────────────────────────
def payload(html):
    m = re.search(r'(var I18N=)(\{.*?\})(;\n  var SUP)', html, re.S)
    return m, json.loads(m.group(2))


def inner_html(html, key):
    """A data-i18n="key" elem belseje a forrásból (magyar szöveg)."""
    m = re.search(r'<(\w+)[^>]*\bdata-i18n="%s"[^>]*>' % re.escape(key), html)
    if not m:
        return None
    tag, i = m.group(1), m.end()
    depth, pos = 1, i
    op = re.compile(r'<(/?)%s\b' % tag)
    while depth:
        mm = op.search(html, pos)
        if not mm:
            return None
        depth += -1 if mm.group(1) else 1
        pos = mm.end()
        if depth == 0:
            return html[i:mm.start()]
    return None


def set_inner(html, key, value):
    """A data-i18n="key" elem belsejének cseréje, beágyazott azonos tagre is figyelve."""
    m = re.search(r'<(\w+)[^>]*\bdata-i18n="%s"[^>]*>' % re.escape(key), html)
    if not m:
        return html
    tag, i = m.group(1), m.end()
    depth, pos = 1, i
    op = re.compile(r'<(/?)%s\b' % tag)
    while depth:
        mm = op.search(html, pos)
        if not mm:
            return html
        depth += -1 if mm.group(1) else 1
        pos = mm.end()
        if depth == 0:
            return html[:i] + value + html[mm.start():]
    return html


def text_of(s):
    """Sima szöveg a markupból: tagek el, entitások feloldva (a JSON-LD és az llms.txt nem HTML)."""
    return re.sub(r'\s+', ' ', htmllib.unescape(re.sub(r'<[^>]+>', '', s))).strip()


def t(dic, lang, key, hu_html):
    """Fordítás vagy magyar eredeti."""
    if lang == 'hu':
        return hu_html.get(key, '')
    return dic[lang].get(key, hu_html.get(key, ''))


# ─────────────────────────── JSON-LD ───────────────────────────
def build_jsonld(lang, dic, hu):
    def tx(key):
        return text_of(t(dic, lang, key, hu))

    faq = []
    for i in range(1, 8):
        q, a = tx('q%d' % i), tx('a%d' % i)
        if q and a:
            faq.append({"@type": "Question", "name": q,
                        "acceptedAnswer": {"@type": "Answer", "text": a}})
    offers = []
    for i in range(1, 6):
        n, dsc = tx('svc%d_t' % i), tx('svc%d_d' % i)
        if n:
            offers.append({"@type": "Offer", "itemOffered": {
                "@type": "Service", "name": n, "description": dsc,
                "provider": {"@id": SITE + "/#person"}}})

    person = {
        "@type": "Person", "@id": SITE + "/#person",
        "name": "Nemes Péter", "url": SITE + PATH[lang],
        "jobTitle": JOB[lang],
        "description": tx('_desc') or tx('hero_sub'),
        "email": "mailto:pr.nemes@gmail.com",
        "telephone": "+36205493710",
        "image": SITE + "/images/profil.jpg",
        "sameAs": ["https://github.com/MayyDayy99"],
        "knowsAbout": KNOWS,
        "knowsLanguage": [{"@type": "Language", "name": l} for l in LANGS],
    }
    service = {
        "@type": "ProfessionalService", "@id": SITE + "/#service",
        "name": "Nemes Péter · " + JOB[lang],
        "url": SITE + PATH[lang],
        "description": tx('_desc') or tx('hero_sub'),
        "provider": {"@id": SITE + "/#person"},
        "image": SITE + "/images/og.jpg",
        "email": "mailto:pr.nemes@gmail.com",
        "telephone": "+36205493710",
        "areaServed": [{"@type": "Country", "name": "Hungary"},
                       {"@type": "Place", "name": REMOTE[lang]}],
        "availableLanguage": [{"@type": "Language", "name": l} for l in LANGS],
        "hasOfferCatalog": {"@type": "OfferCatalog", "name": CATALOG[lang],
                            "itemListElement": offers},
    }
    website = {
        "@type": "WebSite", "@id": SITE + "/#website",
        "url": SITE + PATH[lang], "name": "Nemes Péter · " + JOB[lang],
        "inLanguage": lang, "publisher": {"@id": SITE + "/#person"},
    }
    graph = [person, service, website]
    if faq:
        graph.append({"@type": "FAQPage", "@id": SITE + PATH[lang] + "#faq",
                      "inLanguage": lang, "mainEntity": faq})
    return json.dumps({"@context": "https://schema.org", "@graph": graph},
                      ensure_ascii=False, separators=(',', ':'))


def hreflang_block(current):
    out = []
    for l in LANGS:
        out.append('<link rel="alternate" hreflang="%s" href="%s%s">' % (l, SITE, PATH[l]))
    out.append('<link rel="alternate" hreflang="x-default" href="%s/">' % SITE)
    return '\n'.join(out)


MARK_A, MARK_B = '<!-- geo:start -->', '<!-- geo:end -->'


def put_geo(html, lang, block):
    """A hreflang + JSON-LD blokk beillesztése vagy cseréje a head végén."""
    new = '%s\n%s\n<script type="application/ld+json">%s</script>\n%s' % (MARK_A, block[0], block[1], MARK_B)
    if MARK_A in html:
        return re.sub(re.escape(MARK_A) + r'.*?' + re.escape(MARK_B), lambda _: new, html, flags=re.S)
    return html.replace('</head>', new + '\n</head>', 1)


# ─────────────────────────── nyelvi oldal ───────────────────────────
NAV_SWITCHER = '''<script>
/* Nyelvváltás a statikus aloldalakon: minden nyelvnek saját címe van */
(function(){
  var URLS={hu:'/',en:'/en/',es:'/es/',zh:'/zh/',de:'/de/',fr:'/fr/'};
  function go(l){ try{localStorage.setItem('site_lang',l);}catch(e){} location.href=URLS[l]||'/'; }
  var btn=document.getElementById('langBtn'), box=document.getElementById('lang'), menu=document.getElementById('langMenu');
  if(btn&&box&&menu){
    btn.addEventListener('click',function(e){ e.stopPropagation(); var o=box.classList.toggle('open'); btn.setAttribute('aria-expanded',o?'true':'false'); });
    menu.addEventListener('click',function(e){ var b=e.target.closest('button[data-lang]'); if(!b) return; go(b.getAttribute('data-lang')); });
    document.addEventListener('click',function(e){ if(!box.contains(e.target)){ box.classList.remove('open'); btn.setAttribute('aria-expanded','false'); } });
    document.addEventListener('keydown',function(e){ if(e.key==='Escape'){ box.classList.remove('open'); btn.setAttribute('aria-expanded','false'); } });
  }
  var wlang=document.getElementById('welcomeLang');
  if(wlang) wlang.addEventListener('click',function(e){ var b=e.target.closest('button[data-wlang]'); if(!b) return; go(b.getAttribute('data-wlang')); });
})();
</script>'''


def build_lang_page(src, lang, dic, hu):
    h = src

    # 1) minden data-i18n elem tartalma a fordításra cserélve
    for key in hu:
        v = dic[lang].get(key)
        if v is not None:
            h = set_inner(h, key, v)

    # 2) fej: nyelv, meta, canonical
    h = h.replace('<html lang="hu">', '<html lang="%s">' % lang, 1)
    g = dic[lang].get
    def meta(pat, val):
        nonlocal h
        if val:
            h = re.sub(pat, lambda m: m.group(1) + val.replace('\\', '\\\\') + m.group(2), h, count=1)
    if g('_title'):
        h = re.sub(r'(<title>).*?(</title>)', lambda m: m.group(1) + g('_title') + m.group(2), h, count=1, flags=re.S)
    meta(r'(<meta name="description" content=")[^"]*(">)', g('_desc'))
    meta(r'(<meta property="og:title" content=")[^"]*(">)', g('_ogtitle'))
    meta(r'(<meta property="og:description" content=")[^"]*(">)', g('_ogdesc'))
    meta(r'(<meta property="og:image:alt" content=")[^"]*(">)', g('_ogalt'))
    meta(r'(<meta name="twitter:title" content=")[^"]*(">)', g('_ogtitle'))
    meta(r'(<meta name="twitter:description" content=")[^"]*(">)', g('_ogdesc'))
    h = h.replace('<meta property="og:locale" content="hu_HU">',
                  '<meta property="og:locale" content="%s">' % LOCALE[lang], 1)
    h = h.replace('<link rel="canonical" href="%s/">' % SITE,
                  '<link rel="canonical" href="%s%s">' % (SITE, PATH[lang]), 1)
    h = h.replace('<meta property="og:url" content="%s/">' % SITE,
                  '<meta property="og:url" content="%s%s">' % (SITE, PATH[lang]), 1)

    # 3) poszterek nyelvi változatra égetve (a JS-es cserélő itt már nem fut)
    sfx = '_' + lang
    def poster(m):
        whole, base = m.group(0), m.group(1)
        new = 'images/%s%s.jpg' % (base, sfx)
        if not os.path.exists(os.path.join(ROOT, new)):
            return whole
        whole = re.sub(r'(src|data-poster)="images/[^"]*"', lambda mm: '%s="%s"' % (mm.group(1), new), whole)
        return whole
    h = re.sub(r'<(?:img|video)\b[^>]*\bdata-pl="([a-z0-9_]+)"[^>]*>', poster, h)

    # 4) beágyazott ábra nyelve
    h = h.replace('<iframe src="lokalis-ai-abra.html"',
                  '<iframe src="/lokalis-ai-abra.html?lang=%s"' % lang, 1)

    # 5) relatív útvonalak gyökér-abszolútra (az aloldal egy szinttel lejjebb van)
    h = re.sub(r'\b(src|href|data-poster)="(images/|videos/)', lambda m: '%s="/%s' % (m.group(1), m.group(2)), h)
    h = re.sub(r'\bhref="(szerkeszto-demo|ink-demo|lokalis-ai-abra)\.html"',
               lambda m: 'href="/%s.html"' % m.group(1), h)

    # 6) nyelvválasztó állapota beégetve
    h = h.replace('<span class="lang-cur">HU</span>', '<span class="lang-cur">%s</span>' % lang.upper(), 1)
    h = re.sub(r'(<button type="button" data-lang="([a-z]{2})" role="option">)',
               lambda m: m.group(1).replace('role="option">',
                                            'role="option" aria-selected="%s">' % ('true' if m.group(2) == lang else 'false')), h)
    h = re.sub(r'(<button type="button" data-wlang="([a-z]{2})">)',
               lambda m: m.group(1).replace('">', '" aria-pressed="%s">' % ('true' if m.group(2) == lang else 'false'), 1), h)

    # 7) az i18n motor helyére navigáló nyelvváltó (a szótár így nem terheli az aloldalt)
    eng = re.search(r'<script>\n/\* ===== Többnyelvűség.*?\n</script>', h, re.S)
    assert eng, 'i18n motor nem található'
    h = h[:eng.start()] + NAV_SWITCHER + h[eng.end():]

    # 8) hreflang + JSON-LD
    h = put_geo(h, lang, (hreflang_block(lang), build_jsonld(lang, dic, hu)))
    return h


# ─────────────────────────── crawler-fájlok ───────────────────────────
def write_crawler_files(dic, hu):
    today = datetime.date.today().isoformat()
    bots = ['GPTBot', 'OAI-SearchBot', 'ChatGPT-User', 'ClaudeBot', 'Claude-User',
            'Claude-SearchBot', 'anthropic-ai', 'PerplexityBot', 'Perplexity-User',
            'Google-Extended', 'Googlebot', 'Bingbot', 'Applebot', 'Applebot-Extended',
            'CCBot', 'Amazonbot', 'meta-externalagent', 'DuckDuckBot', 'YandexBot',
            'Bytespider', 'cohere-ai', 'MistralAI-User']
    robots = ['# Minden crawler, az AI-asszisztensekéi is, szívesen látott vendég.', '']
    for b in bots:
        robots += ['User-agent: %s' % b, 'Allow: /', '']
    robots += ['User-agent: *', 'Allow: /', '',
               'Sitemap: %s/sitemap.xml' % SITE, '']
    open(os.path.join(ROOT, 'robots.txt'), 'w', encoding='utf-8').write('\n'.join(robots))

    urls = [(SITE + PATH[l], l) for l in LANGS]
    extra = ['/lokalis-ai-abra.html', '/szerkeszto-demo.html']
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
          'xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for u, l in urls:
        sm.append('  <url>')
        sm.append('    <loc>%s</loc>' % u)
        sm.append('    <lastmod>%s</lastmod>' % today)
        for l2 in LANGS:
            sm.append('    <xhtml:link rel="alternate" hreflang="%s" href="%s%s"/>' % (l2, SITE, PATH[l2]))
        sm.append('    <xhtml:link rel="alternate" hreflang="x-default" href="%s/"/>' % SITE)
        sm.append('    <priority>%s</priority>' % ('1.0' if l == 'hu' else '0.8'))
        sm.append('  </url>')
    for e in extra:
        sm += ['  <url>', '    <loc>%s%s</loc>' % (SITE, e),
               '    <lastmod>%s</lastmod>' % today, '    <priority>0.5</priority>', '  </url>']
    sm.append('</urlset>')
    open(os.path.join(ROOT, 'sitemap.xml'), 'w', encoding='utf-8').write('\n'.join(sm) + '\n')

    def tx(k, lang='hu'):
        return text_of(t(dic, lang, k, hu))

    L = ['# Nemes Péter · %s' % JOB['hu'], '',
         '> %s' % tx('_desc'), '',
         'Egyéni vállalkozó Magyarországról, magánszemélyeknek és kisvállalkozásoknak dolgozom, '
         'távmunkában világszerte. Az első, 30 perces egyeztetés díjmentes.', '',
         '- Kapcsolat: pr.nemes@gmail.com · +36 20 549 3710',
         '- Honlap: %s/' % SITE,
         '- GitHub: https://github.com/MayyDayy99',
         '- Nyelvek: magyar, angol, spanyol, kínai, német, francia', '',
         '## Szolgáltatások', '']
    for i in range(1, 6):
        L.append('### %s' % tx('svc%d_t' % i))
        L.append(tx('svc%d_d' % i))
        L.append('')
    L += ['## Gyakori kérdések', '']
    for i in range(1, 8):
        q, a = tx('q%d' % i), tx('a%d' % i)
        if q:
            L += ['### %s' % q, a, '']
    L += ['## Nyelvi változatok', '']
    for l in LANGS:
        L.append('- [%s](%s%s)' % (l, SITE, PATH[l]))
    L += ['', '## Munkák', '',
          'Minden projekthez működő demó és videó tartozik a honlapon. '
          'A teljes lista a %s/#munkak címen található.' % SITE, '']
    open(os.path.join(ROOT, 'llms.txt'), 'w', encoding='utf-8').write('\n'.join(L))
    return len(bots), len(urls) + len(extra)


# ─────────────────────────── futtatás ───────────────────────────
def main():
    src = open(SRC, encoding='utf-8').read()
    m, dic = payload(src)
    keys = sorted(set(re.findall(r'data-i18n="([a-z0-9_]+)"', src[:m.start()])))
    hu = {}
    for k in keys:
        v = inner_html(src, k)
        if v is not None:
            hu[k] = v
    for k in ['_title', '_desc', '_ogtitle', '_ogdesc', '_ogalt']:
        mm = {'_title': r'<title>(.*?)</title>',
              '_desc': r'<meta name="description" content="([^"]*)"',
              '_ogtitle': r'<meta property="og:title" content="([^"]*)"',
              '_ogdesc': r'<meta property="og:description" content="([^"]*)"',
              '_ogalt': r'<meta property="og:image:alt" content="([^"]*)"'}[k]
        r = re.search(mm, src, re.S)
        if r:
            hu[k] = r.group(1)

    # 1) magyar oldal: hreflang + JSON-LD
    out = put_geo(src, 'hu', (hreflang_block('hu'), build_jsonld('hu', dic, hu)))
    open(SRC, 'w', encoding='utf-8').write(out)
    print('index.html  hreflang + JSON-LD kész (%d kulcs, %d GYIK)' %
          (len(hu), sum(1 for i in range(1, 9) if 'q%d' % i in hu)))

    # 2) nyelvi aloldalak
    for lang in GEN:
        page = build_lang_page(out, lang, dic, hu)
        d = os.path.join(ROOT, lang)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(page)
        print('  /%s/index.html  %d KB' % (lang, len(page.encode()) // 1024))

    # 3) crawler-fájlok
    nb, nu = write_crawler_files(dic, hu)
    print('robots.txt (%d bot), sitemap.xml (%d URL), llms.txt kész' % (nb, nu))


if __name__ == '__main__':
    main()
