/**
 * Poszt-híd: WordPress-alakú kérést fogad, és GitHub repository_dispatch-csé alakítja.
 *
 * Akkor kell, ha a tartalomposztoló csak "végpont + jelszó" módon tud küldeni,
 * és nem tudja beállítani a GitHub által várt event_type / client_payload alakot.
 * Ha a posztoló tudja azt az alakot, erre a hídra nincs szükség: küldjön
 * közvetlenül a GitHub /dispatches végpontra.
 *
 * Beállítandó változók (Cloudflare Worker -> Settings -> Variables):
 *   REPO       pl. MayyDayy99/myPortfolio            (sima változó)
 *   BRIDGE_KEY a posztolóba írt jelszó/kulcs         (Secret)
 *   GH_TOKEN   fine-grained GitHub token, Contents: write  (Secret)
 *
 * A posztolóba ez kerül:
 *   végpont:  https://<worker>.workers.dev/wp-json/wp/v2/posts
 *   kulcs:    ugyanaz, mint a BRIDGE_KEY
 */

const JSON_HEADERS = {
  'content-type': 'application/json; charset=utf-8',
  'access-control-allow-origin': '*',
  'access-control-allow-headers': 'authorization, content-type',
  'access-control-allow-methods': 'GET, POST, OPTIONS',
};

const reply = (status, obj) =>
  new Response(JSON.stringify(obj), { status, headers: JSON_HEADERS });

// Állandó idejű összehasonlítás, hogy a kulcs ne legyen kitalálható a válaszidőből.
function sameKey(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

// A kulcs jöhet Basic (user:jelszó) vagy Bearer fejlécben, vagy ?key= paraméterben.
function presentedKey(req, url) {
  const h = req.headers.get('authorization') || '';
  if (/^basic /i.test(h)) {
    try {
      const decoded = atob(h.slice(6).trim());
      const i = decoded.indexOf(':');
      return i === -1 ? decoded : decoded.slice(i + 1);
    } catch { return ''; }
  }
  if (/^bearer /i.test(h)) return h.slice(7).trim();
  return url.searchParams.get('key') || '';
}

function text(v) {
  if (v == null) return '';
  if (typeof v === 'object') return String(v.raw ?? v.rendered ?? '');
  return String(v);
}

async function readBody(req) {
  const ct = (req.headers.get('content-type') || '').toLowerCase();
  if (ct.includes('application/json')) {
    try { return await req.json(); } catch { return {}; }
  }
  if (ct.includes('form')) {
    const f = await req.formData();
    return Object.fromEntries([...f.entries()]);
  }
  const raw = await req.text();
  try { return JSON.parse(raw); } catch { return {}; }
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);

    if (req.method === 'OPTIONS') return new Response(null, { headers: JSON_HEADERS });

    // Néhány posztoló előbb megnézi, él-e a végpont, és hogy jó-e a kulcs.
    if (req.method === 'GET') {
      if (url.pathname.includes('/users/me')) {
        const ok = sameKey(presentedKey(req, url), env.BRIDGE_KEY || '');
        return ok
          ? reply(200, { id: 1, name: 'poszt-hid', slug: 'poszt-hid' })
          : reply(401, { code: 'rest_not_logged_in', message: 'Hibás kulcs.' });
      }
      return reply(200, {
        name: 'poszt-hid',
        description: 'WordPress-alakú posztot fogad, GitHub Actionsbe továbbítja.',
        routes: { '/wp-json/wp/v2/posts': { methods: ['POST'] } },
      });
    }

    if (req.method !== 'POST') return reply(405, { message: 'Csak POST.' });

    if (!env.BRIDGE_KEY || !env.GH_TOKEN || !env.REPO) {
      return reply(500, { message: 'A hídon hiányzik a REPO, BRIDGE_KEY vagy GH_TOKEN változó.' });
    }
    if (!sameKey(presentedKey(req, url), env.BRIDGE_KEY)) {
      return reply(401, { code: 'rest_cannot_create', message: 'Hibás kulcs.' });
    }

    let d = await readBody(req);
    for (const k of ['post', 'data', 'payload']) {
      if (d && typeof d[k] === 'object' && d[k] !== null) { d = d[k]; break; }
    }

    const title = text(d.title ?? d.cim).trim();
    const content = text(d.content ?? d.body ?? d.tartalom);
    if (!title || !content) {
      return reply(400, { code: 'missing_fields', message: 'title és content kell.' });
    }

    let tags = d.tags ?? d.cimkek ?? [];
    if (typeof tags === 'string') tags = tags.split(',').map(t => t.trim()).filter(Boolean);
    if (!Array.isArray(tags)) tags = [];

    const post = {
      title,
      content,
      excerpt: text(d.excerpt ?? d.leiras).trim(),
      date: String(d.date ?? d.datum ?? '').slice(0, 10),
      slug: d.slug ? String(d.slug) : undefined,
      cover: d.cover ?? d.kep ?? undefined,
      tags,
      status: d.status ? String(d.status) : undefined,
    };
    for (const k of Object.keys(post)) if (post[k] === undefined || post[k] === '') delete post[k];

    const gh = await fetch(`https://api.github.com/repos/${env.REPO}/dispatches`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${env.GH_TOKEN}`,
        accept: 'application/vnd.github+json',
        'content-type': 'application/json',
        'user-agent': 'poszt-hid',
      },
      body: JSON.stringify({ event_type: 'new-post', client_payload: post }),
    });

    if (!gh.ok) {
      const body = await gh.text();
      return reply(502, { code: 'github_error', status: gh.status, message: body.slice(0, 500) });
    }

    // WordPress-szerű válasz, hogy a posztoló sikeresnek lássa.
    return reply(201, {
      id: Date.now(),
      status: post.status === 'draft' ? 'draft' : 'publish',
      slug: post.slug || '',
      link: 'https://portfolio.maydayprod.app/blog/',
      title: { rendered: title },
    });
  },
};
