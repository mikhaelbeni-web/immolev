// Passerelle Claude d'Immolev.
// Le logiciel installé appelle ce serveur avec le compte Immolev de l'utilisateur (en-tête x-api-key = "identifiant:motdepasse").
// La clé Anthropic n'existe qu'ici : variable d'environnement Vercel ANTHROPIC_API_KEY (et ANTHROPIC_WORKSPACE_ID si la clé est multi-espaces). Aucun utilisateur ne la voit.
//   POST /api/ia/v1/messages  -> (réécrit en /api/ia?p=v1&p=messages) transmis à Anthropic (modèles autorisés seulement)
//   GET  /api/ia/ping         -> {"ok":true,"cle":true|false} : le compte est accepté, le serveur a-t-il sa clé ?
// Comptes : variable IMMOLEV_COMPTES = "identifiant:sha256(identifiant:motdepasse);…" (la même que pour /telecharger).
import { createHash, timingSafeEqual } from 'node:crypto';

const MODELES = new Set((process.env.IMMOLEV_MODELES || 'claude-haiku-5-5,claude-sonnet-5-5,claude-opus-5-5').split(',').map((m) => m.trim()));
const MAX_OCTETS = 4 * 1024 * 1024;  // limite des fonctions Vercel : 4,5 Mo
const AMONT = () => (process.env.ANTHROPIC_UPSTREAM || 'https://api.anthropic.com').replace(/\/$/, '');

const egal = (a, b) => a.length === b.length && timingSafeEqual(Buffer.from(a), Buffer.from(b));

function compte(req) {
  const brut = String(req.headers['x-api-key'] || String(req.headers.authorization || '').replace(/^Bearer\s+/i, ''));
  const i = brut.indexOf(':');
  if (i < 1) return null;
  const id = brut.slice(0, i), mdp = brut.slice(i + 1);
  const comptes = Object.fromEntries((process.env.IMMOLEV_COMPTES || '').split(';').filter(Boolean).map((c) => c.split(':')));
  const attendu = comptes[id];
  const empreinte = createHash('sha256').update(`${id}:${mdp}`).digest('hex');
  return attendu && egal(attendu, empreinte) ? id : null;
}

function repondre(res, code, corps, type = 'application/json') {
  res.statusCode = code;
  res.setHeader('Content-Type', type);
  res.setHeader('Cache-Control', 'no-store');
  res.end(typeof corps === 'string' ? corps : JSON.stringify(corps));
}
const erreur = (res, code, type, message) => repondre(res, code, { type: 'error', error: { type, message } });

async function lire(req) {
  const blocs = [];
  let total = 0;
  for await (const bloc of req) {
    total += bloc.length;
    if (total > MAX_OCTETS) return null;
    blocs.push(bloc);
  }
  return Buffer.concat(blocs);
}

export default async function handler(req, res) {
  // vercel.json réécrit /api/ia/<a>/<b> en /api/ia?p=<a>&p=<b> : le chemin voulu est la suite des paramètres « p ».
  const url = new URL(req.url, 'http://x');
  const morceaux = url.searchParams.getAll('p').flatMap((m) => m.split('/')).filter(Boolean);
  const chemin = morceaux.length ? '/' + morceaux.join('/') : url.pathname.replace(/^\/api\/ia/, '').replace(/\/$/, '');
  url.searchParams.delete('p');
  const id = compte(req);
  if (!id) return erreur(res, 401, 'authentication_error', "Compte Immolev refusé : vérifiez l'identifiant et le mot de passe.");

  if (req.method === 'GET' && chemin === '/ping') return repondre(res, 200, { ok: true, cle: !!process.env.ANTHROPIC_API_KEY });
  if (req.method !== 'POST' || chemin !== '/v1/messages') return erreur(res, 404, 'not_found_error', `Route non autorisée (${req.method} ${chemin || '/'}).`);
  const cle = process.env.ANTHROPIC_API_KEY;
  if (!cle) return erreur(res, 503, 'api_error', "Le serveur Immolev n'a pas encore sa clé IA : prévenez Immolev.");

  const corps = await lire(req);
  if (!corps) return erreur(res, 413, 'request_too_large', 'Demande trop volumineuse (4 Mo maximum).');
  let modele = '';
  try { modele = String(JSON.parse(corps.toString('utf-8')).model || ''); } catch (e) { return erreur(res, 400, 'invalid_request_error', 'Corps JSON illisible.'); }
  if (!MODELES.has(modele)) return erreur(res, 403, 'permission_error', `Modèle non autorisé : ${modele || 'aucun'}.`);

  const debut = Date.now();
  // Authorization: Bearer est l'en-tête documenté par Anthropic (valable pour tous les types de clé) ; ANTHROPIC_WORKSPACE_ID
  // est nécessaire seulement avec une clé multi-espaces de travail (colonne « Organisation » de la console).
  const entetes = { 'content-type': 'application/json', authorization: `Bearer ${cle}`, 'anthropic-version': String(req.headers['anthropic-version'] || '2023-06-01') };
  if (process.env.ANTHROPIC_WORKSPACE_ID) entetes['anthropic-workspace-id'] = process.env.ANTHROPIC_WORKSPACE_ID;
  if (req.headers['anthropic-beta']) entetes['anthropic-beta'] = String(req.headers['anthropic-beta']);
  let amont;
  try {
    amont = await fetch(`${AMONT()}/v1/messages${url.search}`, { method: 'POST', headers: entetes, body: corps });
  } catch (e) {
    console.log(JSON.stringify({ compte: id, modele, statut: 'injoignable' }));
    return erreur(res, 502, 'api_error', "Claude est injoignable depuis le serveur Immolev.");
  }
  const type = amont.headers.get('content-type') || 'application/json';
  res.statusCode = amont.status;
  res.setHeader('Content-Type', type);
  res.setHeader('Cache-Control', 'no-store');
  if (amont.headers.get('request-id')) res.setHeader('request-id', amont.headers.get('request-id'));
  for (const h of ['retry-after', 'x-should-retry']) if (amont.headers.get(h)) res.setHeader(h, amont.headers.get(h));  // le SDK règle ses réessais dessus
  if (type.includes('text/event-stream')) {  // flux : transmis au fil de l'eau
    for await (const bloc of amont.body) res.write(bloc);
    res.end();
    console.log(JSON.stringify({ compte: id, modele, statut: amont.status, ms: Date.now() - debut, flux: true }));
    return;
  }
  const texte = await amont.text();
  let usage = null;
  try { usage = JSON.parse(texte).usage || null; } catch (e) { /* réponse non JSON : transmise telle quelle */ }
  console.log(JSON.stringify({ compte: id, modele, statut: amont.status, ms: Date.now() - debut, usage }));
  res.end(texte);
}
