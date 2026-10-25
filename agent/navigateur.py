"""Pilotage de Chrome par l'agent : lecture du contenu des pages (pas de curseur, pas de capture d'écran).

L'agent lance un Chrome avec un profil dédié. Les sessions restent ouvertes ; quand l'une expire,
se_connecter tape les identifiants du coffre des accès (agent/acces.py) directement dans la page, sur
le seul domaine enregistré : le modèle ne lit ni ne voit jamais un mot de passe.

Règles :
- lire_page, aller_a, suivre_lien, remplir_champ : sans confirmation (rien n'est enregistré).
- cliquer_bouton : confirmation du gestionnaire, car un bouton peut enregistrer ou envoyer.
- cliquer_bouton_sans_risque : sans confirmation, seulement pour les boutons dont le libellé est
  dans BOUTONS_SANS_RISQUE (rechercher, actualiser, afficher…).
Les pages construites en cadres (iframes) sont lues aussi : leurs éléments ont un numéro « cadre.n ».
"""
from __future__ import annotations

import functools
import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page, sync_playwright

from . import acces
from .outils import Outil

DOSSIER_ECRANS = Path(__file__).resolve().parent.parent / "procedures" / "ecrans"

# Repère chaque élément utile par un numéro stable (data-agent-ref) et renvoie une carte de la page.
_JS_CARTE = r"""
(prefixe) => {
  const visible = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
  const libelle = e => {
    if (e.id) { const l = document.querySelector(`label[for="${CSS.escape(e.id)}"]`); if (l) return l.innerText.trim(); }
    const parent = e.closest('label'); if (parent) return parent.innerText.trim();
    return (e.getAttribute('aria-label') || e.getAttribute('placeholder') || e.getAttribute('title') || e.name || e.innerText || e.value || '').trim();
  };
  let n = 0; const elements = [];
  for (const e of document.querySelectorAll('a[href], button, input, select, textarea, [role=tab], [role=button], [role=link]')) {
    if (!visible(e) || e.type === 'hidden') continue;
    const ref = prefixe + String(++n); e.setAttribute('data-agent-ref', ref);
    const tag = e.tagName.toLowerCase();
    const sorte = tag === 'a' || e.getAttribute('role') === 'link' ? 'lien'
      : e.getAttribute('role') === 'tab' ? 'onglet'
      : tag === 'button' || e.getAttribute('role') === 'button' || ['submit','button','reset'].includes(e.type) ? 'bouton'
      : tag === 'select' ? 'liste' : 'champ';
    const item = { ref, sorte, libelle: libelle(e).slice(0, 80) };
    if (sorte === 'champ' || sorte === 'liste') {
      item.type = e.type || tag; item.nom = e.name || e.id || '';
      item.valeur = e.type === 'password' ? '••••' : (e.type === 'checkbox' || e.type === 'radio') ? e.checked : (e.value || '');
      if (tag === 'select') item.options = [...e.options].map(o => o.text.trim()).slice(0, 30);
      if (e.disabled || e.readOnly) item.lecture_seule = true;
    }
    elements.push(item);
  }
  return { url: location.href, titre: document.title, texte: document.body.innerText.slice(0, 60000), elements };
}
"""


BOUTONS_SANS_RISQUE = [r"^(re)?cherch", r"^actualis", r"^rafra[iî]ch", r"^afficher", r"^voir\b", r"^filtrer", r"^trier",
                       r"^suivant$", r"^pr[ée]c[ée]dent$", r"^ok$",
                       r"^(se |me )?connecter$", r"^connexion$", r"^s'identifier$", r"^v[ée]rifier( le code)?$",
                       r"^valider (le )?code$",
                       # bandeaux de cookies : toujours acceptés (consigne du gestionnaire)
                       r"^(tout |tous )accepter$", r"^accepter (tout|tous|tous les cookies|les cookies|et fermer|et continuer)$", r"^tout accepter$",
                       r"^j'accepte (tout|les cookies)$",
                       r"^(accept|allow) all( cookies)?$", r"^(i )?agree$", r"^tout autoriser$", r"^autoriser (tous )?les cookies$"]

# Repère le formulaire de connexion visible : identifiant (u), mot de passe (p), bouton (s), code reçu (c).
_JS_CONNEXION = r"""
() => {
  const visible = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden' && !e.disabled; };
  document.querySelectorAll('[data-agent-login]').forEach(e => e.removeAttribute('data-agent-login'));
  const champs = [...document.querySelectorAll('input')].filter(e => visible(e) && !['hidden','checkbox','radio','submit','button','image'].includes(e.type));
  const mdp = champs.find(e => e.type === 'password');
  const indice = e => [e.name, e.id, e.placeholder, e.getAttribute('aria-label'), e.autocomplete,
                       e.id && document.querySelector(`label[for="${CSS.escape(e.id)}"]`)?.innerText].join(' ');
  const code = champs.find(e => e.type !== 'password' && (e.autocomplete === 'one-time-code' || /otp|sms|2fa|code|v[ée]rification/i.test(indice(e))));
  let ident = champs.find(e => e.autocomplete === 'username');
  if (!ident && mdp) ident = champs.filter(e => e !== mdp && (mdp.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_PRECEDING) && ['text','email','tel',''].includes(e.type)).pop();
  if (!ident && !mdp) ident = champs.find(e => ['text','email'].includes(e.type) && /user|login|mail|identifiant|utilisateur|compte/i.test(indice(e)));
  const zone = (mdp || ident)?.closest('form') || document.body;
  const bouton = [...zone.querySelectorAll('button, input[type=submit], [role=button]')].find(b => visible(b) && (b.type === 'submit' || /connex|connect|identif|valider|suivant|continuer|login|sign/i.test(b.innerText || b.value || '')));
  if (ident) ident.setAttribute('data-agent-login', 'u');
  if (mdp) mdp.setAttribute('data-agent-login', 'p');
  if (bouton) bouton.setAttribute('data-agent-login', 's');
  return { ident: !!ident, mdp: !!mdp, bouton: !!bouton, code: code && !mdp ? (code.getAttribute('data-agent-ref') || '?') : null };
}
"""


MAX_ELEMENTS = 120   # éléments listés par lecture de page
MAX_TEXTE = 5000     # caractères de texte par lecture de page


class Navigateur:
    def __init__(self, page: Page, contexte: BrowserContext | None = None, pw: Any = None,
                 boutons_sans_risque: list[str] | None = None):
        self.page, self.contexte, self._pw = page, contexte, pw
        self.boutons_sans_risque = [re.compile(m, re.I) for m in (boutons_sans_risque or BOUTONS_SANS_RISQUE)]
        self._derniere: dict[str, Any] = {}
        self._cadres: list[Any] = []

    @classmethod
    def lancer(cls, profil: str | Path = "profil-chrome", executable: str | None = None, visible: bool = True) -> "Navigateur":
        pw = sync_playwright().start()
        options: dict[str, Any] = {"headless": not visible}
        if executable:
            options["executable_path"] = executable
        else:
            options["channel"] = "chrome"  # le Chrome installé sur le PC du gestionnaire
            options["chromium_sandbox"] = True  # Playwright ajoute --no-sandbox par défaut
        contexte = pw.chromium.launch_persistent_context(str(profil), **options)
        page = contexte.pages[0] if contexte.pages else contexte.new_page()
        nav = cls(page, contexte, pw)
        nav._lancement = (profil, executable, visible)
        logging.info("Chrome de l'agent lancé (profil %s)", profil)
        return nav

    def fermer(self) -> None:
        for arret in (lambda: self.contexte and self.contexte.close(), lambda: self._pw and self._pw.stop()):
            try:
                arret()
            except Exception:  # noqa: BLE001  déjà fermé
                pass

    def relancer(self) -> None:
        """Chrome a été fermé (fenêtre fermée à la main, plantage) : on le rouvre sur le même profil."""
        lancement = getattr(self, "_lancement", None)
        if not lancement:
            raise RuntimeError("Chrome de l'agent fermé et impossible à relancer.")
        self.fermer()
        derniere = None
        for essai in range(3):  # le profil peut rester verrouillé quelques secondes après la fermeture
            try:
                neuf = Navigateur.lancer(*lancement)
                self.page, self.contexte, self._pw = neuf.page, neuf.contexte, neuf._pw
                logging.warning("Chrome de l'agent relancé après fermeture")
                return
            except Exception as e:  # noqa: BLE001
                derniere = e
                logging.warning("relance de Chrome impossible (essai %d) : %s", essai + 1, e)
                time.sleep(3)
        raise RuntimeError(f"Chrome de l'agent fermé et relance impossible : {derniere}")

    def assurer_page(self) -> None:
        """Page fermée mais Chrome ouvert : on reprend un onglet ; Chrome fermé : on le relance."""
        try:
            if not self.page.is_closed():
                return
            if self.contexte:
                self.page = self.contexte.pages[0] if self.contexte.pages else self.contexte.new_page()
                return
        except Exception:  # noqa: BLE001
            pass
        self.relancer()

    def _element(self, ref: str):
        cadre = self.page.main_frame
        if "." in ref:
            i = int(ref.split(".")[0])
            if i >= len(self._cadres):
                raise LookupError(f"Élément {ref} introuvable : relire la page")
            cadre = self._cadres[i]
        loc = cadre.locator(f'[data-agent-ref="{ref}"]')
        if loc.count() != 1:
            raise LookupError(f"Élément {ref} introuvable : relire la page")
        return loc

    def _attendre(self) -> None:
        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        self.page.wait_for_timeout(random.randint(500, 1200))  # rythme naturel : évite les rafales qui déclenchent les captchas

    def carte(self) -> dict[str, Any]:
        self._cadres = list(self.page.frames)
        carte = self.page.main_frame.evaluate(_JS_CARTE, "")
        for i, cadre in enumerate(self._cadres[1:], start=1):
            try:
                sous = cadre.evaluate(_JS_CARTE, f"{i}.")
            except Exception:
                continue  # cadre vide ou en cours de chargement
            if sous["elements"] or sous["texte"].strip():
                carte["elements"] += sous["elements"]
                carte["texte"] += f"\n--- cadre {i} ---\n" + sous["texte"]
        self._derniere = carte
        return carte

    def lire_page(self) -> str:
        """Page résumée : chaque lecture est renvoyée au modèle et facturée, d'où les plafonds."""
        c = self.carte()
        elements, texte = c["elements"], re.sub(r"\n\s*\n+", "\n", c["texte"]).strip()
        lignes = [f"URL : {c['url']}", f"Titre : {c['titre']}", "Éléments :"]
        lignes += self._lignes(elements[:MAX_ELEMENTS])
        if len(elements) > MAX_ELEMENTS:
            lignes.append(f"  … {len(elements) - MAX_ELEMENTS} autres éléments : utilise chercher_dans_page pour les trouver.")
        lignes.append("Texte de la page :\n" + texte[:MAX_TEXTE])
        if len(texte) > MAX_TEXTE:
            lignes.append(f"… texte coupé ({len(texte)} caractères) : utilise chercher_dans_page pour la suite.")
        return "\n".join(lignes)

    def chercher_dans_page(self, texte: str) -> str:
        """Éléments et lignes de texte de la page qui contiennent un mot (sans tout relire)."""
        c, mot = self.carte(), texte.lower().strip()
        trouves = [e for e in c["elements"] if mot in e["libelle"].lower() or mot in str(e.get("valeur", "")).lower()]
        passages = [l.strip() for l in c["texte"].splitlines() if mot in l.lower()][:40]
        lignes = [f"URL : {c['url']}", f"Éléments contenant « {texte} » :"] + (self._lignes(trouves[:60]) or ["  (aucun)"])
        lignes.append("Lignes de texte :\n" + ("\n".join(l[:300] for l in passages) or "(aucune)"))
        return "\n".join(lignes)

    @staticmethod
    def _lignes(elements: list[dict[str, Any]]) -> list[str]:
        lignes = []
        for e in elements:
            detail = "" if e["sorte"] not in ("champ", "liste") else f" [{e['type']}] = {json.dumps(e['valeur'], ensure_ascii=False)}"
            if e.get("options"):
                detail += f" options={e['options']}"
            if e.get("lecture_seule"):
                detail += " (lecture seule)"
            lignes.append(f"  #{e['ref']} {e['sorte']} « {e['libelle']} »{detail}")
        return lignes

    def aller_a(self, url: str) -> str:
        self.page.goto(url)
        self._attendre()
        return self.lire_page()

    def suivre_lien(self, ref: str) -> str:
        el = self._element(ref)
        sorte = el.evaluate("e => e.tagName === 'A' || ['link','tab'].includes(e.getAttribute('role'))")
        if not sorte:
            return f"#{ref} n'est ni un lien ni un onglet : utiliser cliquer_bouton (avec confirmation)."
        el.click()
        self._attendre()
        return self.lire_page()

    def remplir_champ(self, ref: str, valeur: str) -> str:
        el = self._element(ref)
        info = el.evaluate("e => ({tag: e.tagName.toLowerCase(), type: e.type})")
        if info["type"] == "password":
            return "Refusé : un mot de passe ne se tape pas ainsi. Utiliser se_connecter avec le nom du site."
        if info["tag"] == "select":
            el.select_option(label=valeur)
        elif info["type"] in ("checkbox", "radio"):
            el.set_checked(valeur.lower() in ("1", "oui", "true", "vrai"))
        else:
            el.fill(valeur)
        relu = el.evaluate("e => e.type === 'checkbox' || e.type === 'radio' ? String(e.checked) : (e.tagName === 'SELECT' ? e.options[e.selectedIndex].text : e.value)")
        return f"#{ref} rempli, valeur relue : {relu!r}. Rien n'est enregistré tant qu'aucun bouton n'est cliqué."

    def _formulaire_connexion(self, domaine: str):
        """Premier cadre du domaine enregistré qui montre un formulaire de connexion."""
        for cadre in self.page.frames:
            if not acces.domaine_correspond(urlparse(cadre.url).hostname or "", domaine):
                continue
            try:
                etat = cadre.evaluate(_JS_CONNEXION)
            except Exception:
                continue
            if etat["ident"] or etat["mdp"] or etat["code"]:
                return cadre, etat
        return None, None

    def se_connecter(self, site: str) -> str:
        """Connexion avec le coffre des accès. Les identifiants ne sortent jamais de cette fonction."""
        fiche = acces.trouver(site)
        if not acces.domaine_correspond(urlparse(self.page.url).hostname or "", fiche["domaine"]):
            self.page.goto(fiche["url"])
            self._attendre()
        if fiche.get("mode") == "gmail":
            self.carte()
            return (f"{fiche['nom']} se connecte avec Google, sans mot de passe. Si la page demande de s'identifier, clique sur "
                    "« Se connecter avec Google » (confirmation de l'équipe d'abord), choisis le compte Google " + (fiche.get("gmail") or "de l'agent") + " (si absent de la liste, demande à l'équipe de le connecter dans le panneau Immolev), puis relis la page. "
                    "Si Google refuse ou demande un code, demande-le à l'équipe. Page actuelle :\n" + self.lire_page())
        identifiant, mot_de_passe = acces.identifiants(fiche["id"])
        mdp_tape = False
        for _ in range(3):  # certains sites demandent l'identifiant puis le mot de passe sur un 2e écran
            cadre, etat = self._formulaire_connexion(fiche["domaine"])
            if cadre is None:
                break
            if etat["code"] and not etat["mdp"] and mdp_tape:  # « code utilisateur » avant le mot de passe = identifiant
                self.carte()
                return (f"{fiche['nom']} demande un code de vérification (SMS ou mail). Demande-le à l'équipe dans ta réponse ; "
                        "quand elle l'envoie, relis la page, remplis le champ du code avec remplir_champ puis valide.")
            if etat["mdp"] and mdp_tape:
                break  # le mot de passe est redemandé : refusé
            if etat["ident"]:
                cadre.locator('[data-agent-login="u"]').fill(identifiant)
            if etat["mdp"]:
                cadre.locator('[data-agent-login="p"]').fill(mot_de_passe)
                mdp_tape = True
            if etat["bouton"]:
                cadre.locator('[data-agent-login="s"]').click()
            else:
                cadre.locator('[data-agent-login="p"], [data-agent-login="u"]').last.press("Enter")
            self._attendre()
        cadre, etat = self._formulaire_connexion(fiche["domaine"])
        if cadre is not None and etat["mdp"]:
            return (f"Connexion à {fiche['nom']} refusée : le site redemande le mot de passe. Les identifiants du coffre "
                    "sont peut-être faux ou expirés : le gestionnaire doit les corriger dans le panneau Immolev.")
        if cadre is not None and etat["code"] and mdp_tape:
            self.carte()
            return (f"{fiche['nom']} demande un code de vérification (SMS ou mail). Demande-le à l'équipe dans ta réponse ; "
                    "quand elle l'envoie, relis la page, remplis le champ du code avec remplir_champ puis valide.")
        return f"Connecté à {fiche['nom']}.\n" + self.lire_page()

    def cliquer_bouton(self, ref: str) -> str:
        self._element(ref).click()
        self._attendre()
        return "Bouton cliqué. Page après le clic (vérifier que l'enregistrement a réussi) :\n" + self.lire_page()

    def cliquer_bouton_sans_risque(self, ref: str) -> str:
        el = self._element(ref)
        libelle = el.evaluate("e => (e.innerText || e.value || e.getAttribute('aria-label') || '').trim()")
        if not any(m.search(libelle) for m in self.boutons_sans_risque):
            return f"Le bouton « {libelle} » n'est pas dans la liste sans risque : utiliser cliquer_bouton (avec confirmation)."
        el.click()
        self._attendre()
        return self.lire_page()

    def apercu_formulaire(self, ref: str) -> str:
        """Ce que le gestionnaire voit avant de confirmer un clic : le bouton et les champs de son formulaire."""
        el = self._element(ref)
        return el.evaluate(r"""b => {
          const zone = b.closest('form') || document.body;
          const champs = [...zone.querySelectorAll('[data-agent-ref]')].filter(e => ['INPUT','SELECT','TEXTAREA'].includes(e.tagName) && e.type !== 'password' && e.type !== 'hidden');
          const val = e => e.type === 'checkbox' ? (e.checked ? 'oui' : 'non') : e.tagName === 'SELECT' ? e.options[e.selectedIndex]?.text : e.value;
          const lib = e => (e.id && document.querySelector(`label[for="${CSS.escape(e.id)}"]`)?.innerText) || e.closest('label')?.innerText || e.name || e.placeholder || '';
          return `Bouton « ${(b.innerText || b.value || '').trim()} »\n` + champs.map(e => `  ${lib(e).trim()} : ${val(e)}`).join('\n');
        }""")

    def relever_ecran(self, nom: str) -> str:
        """Enregistre la structure de l'écran (libellés et types, jamais les valeurs) pour en faire une procédure."""
        c = self.carte()
        structure = {"nom": nom, "url": re.sub(r"\d{3,}", "{id}", c["url"]), "titre": c["titre"],
                     "elements": [{k: v for k, v in e.items() if k not in ("valeur", "ref")} for e in c["elements"]]}
        DOSSIER_ECRANS.mkdir(parents=True, exist_ok=True)
        chemin = DOSSIER_ECRANS / f"{re.sub(r'[^a-z0-9_-]', '_', nom.lower())}.json"
        chemin.write_text(json.dumps(structure, ensure_ascii=False, indent=2))
        return f"Écran « {nom} » relevé : {len(structure['elements'])} éléments, sans aucune valeur."


FERME = ("has been closed", "Target closed", "Browser closed", "browser has disconnected", "Connection closed")


def _resistant(nav: Navigateur, fonction):
    """Rouvre Chrome s'il a été fermé, puis réessaie une fois."""
    @functools.wraps(fonction)
    def appel(*args, **kwargs):
        nav.assurer_page()
        try:
            return fonction(*args, **kwargs)
        except Exception as e:
            if not any(m.lower() in str(e).lower() for m in FERME):
                raise
            logging.warning("%s : Chrome fermé pendant l'action (%s), relance", fonction.__name__, str(e).splitlines()[0])
            nav.relancer()
            return fonction(*args, **kwargs)
    return appel


def outils_navigateur(nav: Navigateur) -> dict[str, Outil]:
    ref = {"ref": {"type": "string", "description": "Numéro #ref lu par lire_page"}}
    outils = [
        Outil("lire_page", "Lit la page affichée dans Chrome : URL, champs avec leurs valeurs, boutons, liens, texte.", {}, False, nav.lire_page),
        Outil("chercher_dans_page", "Cherche un mot dans la page affichée (éléments et lignes de texte) sans tout relire : moins cher que lire_page sur une longue page.",
              {"texte": {"type": "string"}}, False, nav.chercher_dans_page),
        Outil("aller_a", "Ouvre n'importe quelle adresse dans Chrome (logiciel de gestion, banque, impots.gouv, messagerie, tout autre site).",
              {"url": {"type": "string"}}, False, nav.aller_a),
        Outil("suivre_lien", "Clique sur un lien ou un onglet pour naviguer. Refusé sur un bouton.", ref, False, nav.suivre_lien),
        Outil("remplir_champ", "Remplit un champ, une liste ou une case de la page (non enregistré tant qu'aucun bouton n'est cliqué). Jamais de mot de passe.",
              {**ref, "valeur": {"type": "string"}}, False, nav.remplir_champ),
        Outil("cliquer_bouton_sans_risque", "Clique sans confirmation sur un bouton qui ne modifie rien (Rechercher, Actualiser, Afficher, Filtrer, Suivant…). Refusé pour tout autre bouton.",
              ref, False, nav.cliquer_bouton_sans_risque),
        Outil("cliquer_bouton", "Clique sur un bouton (enregistrer, valider, envoyer, rechercher…). Après le clic, vérifier la page.", ref, True, nav.cliquer_bouton),
        Outil("se_connecter", "Se connecte à un site du coffre des accès (logiciel de copropriété, banque, impots.gouv…) quand une page demande de s'identifier. "
              "Tape l'identifiant et le mot de passe enregistrés par le gestionnaire sans que tu les voies ; pour un site en mode Gmail, ouvre la page et tu cliques « Se connecter avec Google » avec le Gmail enregistré pour ce site. Ne demande jamais d'identifiants à l'équipe.",
              {"site": {"type": "string", "description": "Nom du site, ex. Banque pro, Impots pro, Logiciel copro"}}, False, nav.se_connecter),
        Outil("relever_ecran", "Mémorise la structure de l'écran actuel sous un nom (ex. 'copro_fiche_lot') pour en faire une procédure. Aucune valeur n'est enregistrée.",
              {"nom": {"type": "string"}}, False, nav.relever_ecran),
    ]
    for o in outils:
        o.executer = _resistant(nav, o.executer)
    return {o.nom: o for o in outils}
