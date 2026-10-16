// Espace protégé /telecharger : compte + mot de passe (authentification HTTP « Basic »).
// Comptes dans la variable d'environnement Vercel OPTIZIEN_COMPTES = "identifiant:sha256(identifiant:motdepasse);…"
export const config = { matcher: ['/telecharger', '/telecharger/:path*'] };

async function empreinte(texte) {
  const octets = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(texte));
  return [...new Uint8Array(octets)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export default async function middleware(requete) {
  const entete = requete.headers.get('authorization') || '';
  if (entete.startsWith('Basic ')) {
    let identifiant = '', motDePasse = '';
    try {
      const brut = new TextDecoder().decode(Uint8Array.from(atob(entete.slice(6)), (c) => c.charCodeAt(0)));
      const i = brut.indexOf(':');
      identifiant = brut.slice(0, i);
      motDePasse = brut.slice(i + 1);
    } catch (e) { /* entête illisible : refusé */ }
    const comptes = Object.fromEntries((process.env.OPTIZIEN_COMPTES || '').split(';').filter(Boolean).map((c) => c.split(':')));
    if (identifiant && comptes[identifiant] && comptes[identifiant] === await empreinte(`${identifiant}:${motDePasse}`)) {
      return new Response(null, { headers: { 'x-middleware-next': '1' } });  // laisse passer
    }
  }
  return new Response('Accès réservé aux magasins Optizien.', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Optizien", charset="UTF-8"', 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
