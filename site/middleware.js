// Espace client : page de connexion /espace (identifiant + mot de passe) qui pose un cookie de session signé.
// Le logiciel (mises à jour en ligne) continue d'envoyer l'entête « Authorization: Basic ».
// Comptes dans la variable Vercel IMMOLEV_COMPTES = "identifiant:sha256(identifiant:motdepasse);…"
// Clé de signature : IMMOLEV_SECRET si définie, sinon dérivée des comptes.
export const config = { matcher: ['/espace', '/telecharger', '/telecharger/:path*', '/espace/connexion', '/espace/deconnexion'] };

const COOKIE = 'oz_session';
const DUREE = 30 * 24 * 3600;  // 30 jours
const enc = new TextEncoder();
const hex = (b) => [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, '0')).join('');
const empreinte = async (t) => hex(await crypto.subtle.digest('SHA-256', enc.encode(t)));
const comptes = () => Object.fromEntries((process.env.IMMOLEV_COMPTES || '').split(';').filter(Boolean).map((c) => c.split(':')));
const suivant = () => new Response(null, { headers: { 'x-middleware-next': '1' } });
const vers = (url, entetes = {}) => new Response(null, { status: 303, headers: { Location: url, 'Cache-Control': 'no-store', ...entetes } });

function egal(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

async function verifier(id, mdp) {
  const h = comptes()[id];
  return !!(id && h && egal(h, await empreinte(`${id}:${mdp}`)));
}

async function signature(charge) {
  const cle = await crypto.subtle.importKey('raw', enc.encode(process.env.IMMOLEV_SECRET || 'oz:' + (process.env.IMMOLEV_COMPTES || '')),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return hex(await crypto.subtle.sign('HMAC', cle, enc.encode(charge)));
}

// La signature couvre l'empreinte du compte : changer le mot de passe déconnecte les sessions ouvertes.
async function jeton(id) {
  const fin = Math.floor(Date.now() / 1000) + DUREE;
  return `${encodeURIComponent(id)}.${fin}.${await signature(`${id}.${fin}.${comptes()[id]}`)}`;
}

async function session(requete) {
  const brut = (requete.headers.get('cookie') || '').split(/;\s*/).find((c) => c.startsWith(COOKIE + '='));
  if (!brut) return false;
  const [idc, fin, sig] = brut.slice(COOKIE.length + 1).split('.');
  let id = '';
  try { id = decodeURIComponent(idc || ''); } catch (e) { return false; }
  if (!id || !comptes()[id] || !(Number(fin) > Date.now() / 1000)) return false;
  return egal(sig, await signature(`${id}.${fin}.${comptes()[id]}`));
}

async function basique(requete) {
  const entete = requete.headers.get('authorization') || '';
  if (!entete.startsWith('Basic ')) return null;
  try {
    const brut = new TextDecoder().decode(Uint8Array.from(atob(entete.slice(6)), (c) => c.charCodeAt(0)));
    const i = brut.indexOf(':');
    return await verifier(brut.slice(0, i), brut.slice(i + 1));
  } catch (e) { return false; }
}

export default async function middleware(requete) {
  const url = new URL(requete.url);
  const temoin = (valeur, age) => `${COOKIE}=${valeur}; Path=/; Max-Age=${age}; HttpOnly; Secure; SameSite=Lax`;

  // Déjà connecté : la page de connexion mène directement aux téléchargements.
  if (url.pathname === '/espace') return (await session(requete)) ? vers('/telecharger') : suivant();
  if (url.pathname === '/espace/deconnexion') return vers('/espace?au-revoir', { 'Set-Cookie': temoin('', 0) });

  if (url.pathname === '/espace/connexion') {
    if (requete.method !== 'POST') return vers('/espace');
    let id = '', mdp = '';
    try { const f = await requete.formData(); id = String(f.get('identifiant') || '').trim(); mdp = String(f.get('mot_de_passe') || ''); } catch (e) { /* formulaire illisible */ }
    if (!(await verifier(id, mdp))) return vers('/espace?erreur');
    return vers('/telecharger', { 'Set-Cookie': temoin(await jeton(id), DUREE) });
  }

  // /telecharger : logiciel (entête Basic) ou navigateur (cookie de session)
  const b = await basique(requete);
  if (b || (b === null && await session(requete))) return suivant();
  const page = url.pathname === '/telecharger' || url.pathname === '/telecharger/' || url.pathname === '/telecharger/index.html';
  if (page && b === null) return vers('/espace');
  // Fichiers (version.json, zip) : 401 sans fenêtre de connexion du navigateur.
  return new Response('Accès réservé aux utilisateurs d'Immolev.', { status: 401, headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' } });
}
