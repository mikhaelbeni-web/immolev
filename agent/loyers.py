"""Rapprochement bancaire des loyers et relances des impayés (remplace celui de Rentila).

Fichiers du dossier des données :
- loyers.json : réglages et baux suivis (loyer charges comprises, jour d'échéance, motifs du payeur sur le relevé,
  ajustements d'un mois donné, ex. franchise : {"2026-12": 52.13}).
- relances.json : relances déjà faites (une seule fois par bail, échéance et palier).
- courriers/ : mises en demeure préparées.

Principe : les virements reçus sur les comptes de la société du bail, reconnus au nom du payeur, sont imputés aux
échéances les plus anciennes d'abord (report de solde). Un virement reconnu seulement au montant ne compte pas : il
bloque la relance et il est signalé, jusqu'à ce que le gestionnaire l'associe (associer_operation).

Paliers : rappel amiable (J+5) et relance ferme (J+15) partent seuls par mail quand le mode automatique est activé ;
la mise en demeure (J+30) est préparée et attend toujours la confirmation du gestionnaire.
"""
from __future__ import annotations

import calendar
import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Callable

from . import banque

FICHIER, RELANCES, COURRIERS = "loyers.json", "relances.json", "courriers"
PALIERS = [("rappel", 5), ("relance", 15), ("mise_en_demeure", 30)]
NOMS_PALIERS = {"rappel": "rappel amiable", "relance": "relance ferme", "mise_en_demeure": "mise en demeure"}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
SEUIL = 1.0  # en dessous d'un euro de reste, l'échéance est soldée
REGLAGES_DEFAUT = {
    "debut_suivi": "",          # AAAA-MM : premier mois contrôlé
    "auto": False,              # rappel et relance envoyés seuls (sinon : préparés et signalés)
    "jour_rapport": 6,          # jour du mois du point complet
    "envoi": {"serveur": "", "outil": "envoyer_mail", "compte": ""},
    "signatures": {},           # société → signature des mails et courriers
}


# ---------------------------------------------------------------- fichiers

def _lire(f: Path, defaut: Any) -> Any:
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut


def _ecrire(f: Path, donnees: Any) -> None:
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def charger(dossier: Path) -> dict[str, Any]:
    d = _lire(Path(dossier) / FICHIER, {})
    d["reglages"] = {**REGLAGES_DEFAUT, **d.get("reglages", {})}
    d.setdefault("baux", [])
    d.setdefault("affectations", {})
    return d


def sauver(dossier: Path, d: dict[str, Any]) -> None:
    _ecrire(Path(dossier) / FICHIER, d)


def _simple(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").upper())
    return re.sub(r"[^A-Z0-9]+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


def euros(x: float) -> str:
    return f"{x:,.2f} €".replace(",", " ").replace(".", ",")


def nom_mois(m: str) -> str:
    a, n = m.split("-")
    return f"{MOIS[int(n) - 1]} {a}"


def jj(d: str) -> str:
    return f"{d[8:10]}/{d[5:7]}/{d[:4]}"


# ---------------------------------------------------------------- baux

CHAMPS_BAIL = {"id", "societe", "bien", "locataires", "emails", "adresse", "loyer", "jour_echeance", "debut", "fin",
               "payeurs", "garantie", "cautions", "ajustements", "actif"}


def enregistrer_bail(dossier: Path, bail: dict[str, Any]) -> str:
    """Ajoute ou remplace un bail (par son id). Contrôle les champs utiles au rapprochement."""
    inconnus = set(bail) - CHAMPS_BAIL
    if inconnus:
        raise ValueError(f"Champs inconnus : {', '.join(sorted(inconnus))}. Champs : {', '.join(sorted(CHAMPS_BAIL))}.")
    b = {"locataires": [], "emails": [], "payeurs": [], "cautions": [], "ajustements": {}, "garantie": "", "fin": "",
         "adresse": "", "jour_echeance": 1, "actif": True, **bail}
    b["societe"] = banque.societe_normale(b.get("societe", ""))
    if not str(b.get("id", "")).strip() or not str(b.get("bien", "")).strip():
        raise ValueError("id et bien sont obligatoires (ex. id « livry-2e », bien « Livry 2e étage »).")
    try:
        b["loyer"] = round(float(str(b["loyer"]).replace(",", ".")), 2)
        b["jour_echeance"] = int(b["jour_echeance"])
        date.fromisoformat(b["debut"])
        if b["fin"]:
            date.fromisoformat(b["fin"])
        b["ajustements"] = {m: round(float(v), 2) for m, v in (b["ajustements"] or {}).items() if re.fullmatch(r"\d{4}-\d{2}", m)}
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"Bail incomplet ou mal écrit ({e}) : loyer en euros charges comprises, debut AAAA-MM-JJ.") from None
    if not 1 <= b["jour_echeance"] <= 31:
        raise ValueError("jour_echeance : 1 à 31.")
    if not [p for p in b["payeurs"] if len(_simple(p)) >= 3]:
        raise ValueError("payeurs : au moins un nom tel qu'il apparaît sur le relevé (ex. « GASNIER »).")
    d = charger(dossier)
    d["baux"] = [x for x in d["baux"] if x["id"] != b["id"]] + [b]
    sauver(dossier, d)
    return f"Bail {b['id']} enregistré : {b['bien']}, {euros(b['loyer'])} le {b['jour_echeance']} du mois, {b['societe']}."


def regler(dossier: Path, **valeurs: Any) -> None:
    d = charger(dossier)
    for k, v in valeurs.items():
        if k not in REGLAGES_DEFAUT:
            raise ValueError(f"Réglage inconnu : {k}")
        d["reglages"][k] = v
    sauver(dossier, d)


def associer_operation(dossier: Path, ref: str, bail_id: str) -> str:
    """Rattache un virement à un bail (bail_id) ou l'écarte (« ignorer »). Le nom du payeur est retenu pour la suite."""
    d = charger(dossier)
    op = next((o for o in banque.operations(dossier) if o["ref"] == ref), None)
    if op is None:
        return f"Opération {ref} introuvable dans le relevé."
    if bail_id != "ignorer":
        bail = next((b for b in d["baux"] if b["id"] == bail_id), None)
        if bail is None:
            return f"Bail {bail_id} inconnu. Baux : {', '.join(b['id'] for b in d['baux'])}."
        if op["payeur"] and _simple(op["payeur"]) not in map(_simple, bail["payeurs"]):
            bail["payeurs"].append(op["payeur"])
    d["affectations"][ref] = bail_id
    sauver(dossier, d)
    return f"Virement du {jj(op['date'])} de {euros(op['montant'])} " + ("écarté." if bail_id == "ignorer" else f"rattaché au bail {bail_id}.")


# ---------------------------------------------------------------- échéances et rapprochement

def _echeance(mois: str, jour: int) -> str:
    a, m = map(int, mois.split("-"))
    return date(a, m, min(jour, calendar.monthrange(a, m)[1])).isoformat()


def _mois_suivant(m: str) -> str:
    a, n = map(int, m.split("-"))
    return f"{a + n // 12}-{n % 12 + 1:02d}"


def echeances(bail: dict[str, Any], debut_suivi: str, aujourd_hui: date) -> list[dict[str, Any]]:
    """Échéances dues à ce jour : {mois, date, montant}. Avant le début du bail ou du suivi : rien."""
    if not bail.get("actif", True):
        return []
    m = max(bail["debut"][:7], debut_suivi or bail["debut"][:7])
    fin = bail.get("fin") or "9999-12-31"
    sortie = []
    while True:
        d = _echeance(m, bail["jour_echeance"])
        if d > aujourd_hui.isoformat():
            break
        if bail["debut"][:7] <= m <= fin[:7]:
            montant = bail["ajustements"].get(m, bail["loyer"])
            if montant > 0:
                sortie.append({"mois": m, "date": d, "montant": round(montant, 2)})
        m = _mois_suivant(m)
    return sortie


def _reconnu(bail: dict[str, Any], op: dict[str, Any]) -> bool:
    texte = f" {_simple(op['libelle'])} {_simple(op['payeur'])} "
    return any(f" {_simple(p)} " in texte for p in bail["payeurs"] if len(_simple(p)) >= 3)


def rapprocher(d: dict[str, Any], ops: list[dict[str, Any]], aujourd_hui: date) -> dict[str, Any]:
    """{baux: {id: {echeances: [... avec paye, reste, retard], paiements, solde, bloque}}, inconnus: [...], a_repartir: [...]}"""
    r = d["reglages"]
    baux = [b for b in d["baux"] if b.get("actif", True)]
    debut = r["debut_suivi"] or min((b["debut"][:7] for b in baux), default="")
    plancher = _echeance(debut, 1) if debut else "9999"
    credits = [o for o in ops if o["montant"] > 0 and o["date"] >= _avant(plancher, 10)]
    etat = {b["id"]: {"bail": b, "echeances": echeances(b, r["debut_suivi"], aujourd_hui), "paiements": [], "bloque": ""}
            for b in baux}
    inconnus, a_repartir = [], []
    for o in credits:
        aff = d["affectations"].get(o["ref"])
        if aff == "ignorer":
            continue
        if aff in etat:
            etat[aff]["paiements"].append(o)
            continue
        candidats = [b for b in baux if b["societe"] == o["societe"] and _reconnu(b, o)]
        if len(candidats) == 1:
            etat[candidats[0]["id"]]["paiements"].append(o)
        elif len(candidats) > 1:
            # même payeur pour plusieurs baux (logement + cave) : montant d'une seule échéance, ou de toutes ensemble
            restes = {b["id"]: _reste_avant(etat[b["id"]], o["date"]) for b in candidats}
            seul = [i for i, v in restes.items() if abs(v - o["montant"]) < 0.01]
            if len(seul) == 1:
                etat[seul[0]]["paiements"].append(o)
            elif abs(sum(restes.values()) - o["montant"]) < 0.01:
                for i, v in restes.items():
                    if v > 0:
                        etat[i]["paiements"].append({**o, "montant": round(v, 2), "partage": True})
            else:
                a_repartir.append({**o, "baux": [b["id"] for b in candidats]})
                for b in candidats:
                    etat[b["id"]]["bloque"] = f"virement du {jj(o['date'])} de {euros(o['montant'])} à répartir"
        elif o["date"] >= plancher and o["societe"] in {b["societe"] for b in baux}:
            inconnus.append(o)
    for e in etat.values():
        _imputer(e, aujourd_hui)
    for o in inconnus:  # un virement inconnu du montant exact d'un impayé : ne pas relancer avant de vérifier
        for e in etat.values():
            if e["bail"]["societe"] != o["societe"] or e["bloque"] or e["solde"] <= SEUIL:
                continue
            restes = [x["reste"] for x in e["echeances"] if x["reste"] > SEUIL] + [e["solde"]]
            if any(abs(v - o["montant"]) < 0.01 for v in restes):
                e["bloque"] = f"virement non identifié du {jj(o['date'])} de {euros(o['montant'])}, du même montant"
    return {"baux": etat, "inconnus": inconnus, "a_repartir": a_repartir}


def _avant(d: str, jours: int) -> str:
    return date.fromordinal(date.fromisoformat(d).toordinal() - jours).isoformat() if d != "9999" else d


def _reste_avant(e: dict[str, Any], jour: str) -> float:
    du = sum(x["montant"] for x in e["echeances"] if x["date"] <= _plus(jour, 10))
    return round(du - sum(p["montant"] for p in e["paiements"]), 2)


def _plus(d: str, jours: int) -> str:
    return date.fromordinal(date.fromisoformat(d).toordinal() + jours).isoformat()


def _imputer(e: dict[str, Any], aujourd_hui: date) -> None:
    """Imputation aux échéances les plus anciennes d'abord."""
    dispo = round(sum(p["montant"] for p in e["paiements"]), 2)
    for x in e["echeances"]:
        x["paye"] = round(min(dispo, x["montant"]), 2)
        dispo = round(dispo - x["paye"], 2)
        x["reste"] = round(x["montant"] - x["paye"], 2)
        x["retard"] = (aujourd_hui - date.fromisoformat(x["date"])).days
    e["avance"] = dispo
    e["solde"] = round(sum(x["reste"] for x in e["echeances"]), 2)


# ---------------------------------------------------------------- relances

def _palier(retard: int) -> str | None:
    atteint = [p for p, j in PALIERS if retard >= j]
    return atteint[-1] if atteint else None


def signature(d: dict[str, Any], societe: str) -> str:
    return d["reglages"]["signatures"].get(societe) or f"La gérance\n{societe}"


def texte_relance(d: dict[str, Any], e: dict[str, Any], x: dict[str, Any], palier: str) -> tuple[str, str]:
    b = e["bail"]
    impayees = [y for y in e["echeances"] if y["reste"] > SEUIL]
    detail = "\n".join(f"- loyer de {nom_mois(y['mois'])}, dû le {jj(y['date'])} : {euros(y['reste'])}" for y in impayees)
    total = euros(sum(y["reste"] for y in impayees))
    sujet = f"{b['bien']} : loyer de {nom_mois(x['mois'])}"
    if palier == "rappel":
        corps = (f"Madame, Monsieur,\n\nSauf erreur de notre part, nous n'avons pas encore reçu le règlement de votre loyer de "
                 f"{nom_mois(x['mois'])} ({euros(x['reste'])}), dû le {jj(x['date'])}, pour le logement {b['bien']}.\n\n"
                 "Il s'agit peut-être d'un simple oubli : nous vous remercions de bien vouloir effectuer le virement dans les "
                 "meilleurs délais. Si votre règlement est déjà parti, merci de ne pas tenir compte de ce message.\n\n"
                 "Nous vous prions d'agréer, Madame, Monsieur, nos salutations distinguées.\n\n")
    else:
        sujet = f"Relance : {sujet}"
        corps = (f"Madame, Monsieur,\n\nMalgré notre précédent message, nous restons sans règlement des sommes suivantes "
                 f"pour le logement {b['bien']} :\n{detail}\nSoit un total de {total}.\n\n"
                 "Nous vous demandons de régulariser cette situation sous huit jours. À défaut, nous serons contraints de vous "
                 "adresser une mise en demeure par lettre recommandée.\n\nSi vous rencontrez une difficulté, nous vous invitons "
                 "à nous contacter rapidement pour en parler.\n\nNous vous prions d'agréer, Madame, Monsieur, nos salutations "
                 "distinguées.\n\n")
    return sujet, corps + signature(d, b["societe"])


def courrier_mise_en_demeure(d: dict[str, Any], e: dict[str, Any], aujourd_hui: date) -> str:
    b = e["bail"]
    impayees = [y for y in e["echeances"] if y["reste"] > SEUIL]
    detail = "\n".join(f"- loyer et charges de {nom_mois(y['mois'])}, échu le {jj(y['date'])} : {euros(y['reste'])}" for y in impayees)
    total = euros(sum(y["reste"] for y in impayees))
    caution = ("\nCopie de ce courrier est adressée à la personne qui s'est portée caution de vos engagements.\n"
               if b.get("cautions") else "")
    return (f"{signature(d, b['societe'])}\n\n{', '.join(b['locataires'])}\n{b.get('adresse') or b['bien']}\n\n"
            f"Le {aujourd_hui.strftime('%d/%m/%Y')}\n\nLettre recommandée avec accusé de réception\n\n"
            f"Objet : mise en demeure de payer, loyers impayés, {b['bien']}\n\n"
            f"Madame, Monsieur,\n\nMalgré nos relances, vous restez redevable des sommes suivantes au titre de votre bail :\n"
            f"{detail}\nSoit un total de {total}.\n\n"
            "Par la présente, nous vous mettons en demeure de régler cette somme dans un délai de huit jours à compter de la "
            "réception de ce courrier.\n\nÀ défaut de paiement dans ce délai, nous engagerons sans autre avis la procédure de "
            "recouvrement, notamment la délivrance par commissaire de justice d'un commandement de payer visant la clause "
            "résolutoire du bail, dont les frais resteront à votre charge.\n" + caution +
            "\nNous vous prions d'agréer, Madame, Monsieur, nos salutations distinguées.\n\n" + signature(d, b["societe"]) + "\n")


def _envoyer_mail(d: dict[str, Any], envoyer: Callable[[str, str, dict], str] | None, a: str, sujet: str, texte: str) -> str:
    env = d["reglages"]["envoi"]
    if envoyer is None or not env.get("serveur"):
        raise RuntimeError("aucune boîte d'envoi réglée")
    args = {"destinataire": a, "sujet": sujet, "texte": texte}
    if env.get("compte"):
        args["compte"] = env["compte"]
    rep = envoyer(env["serveur"], env.get("outil") or "envoyer_mail", args)
    if str(rep).startswith("Erreur"):
        raise RuntimeError(str(rep)[:200])
    return rep


def tour(dossier: Path, aujourd_hui: date | None = None, envoyer: Callable[[str, str, dict], str] | None = None,
         client: banque.Client | None = None, relever: bool = True, point_complet: bool | None = None) -> str | None:
    """Tour quotidien : relève la banque, rapproche, fait les relances dues. Renvoie le message pour le gestionnaire,
    ou None s'il n'y a rien à dire aujourd'hui."""
    j = aujourd_hui or date.today()
    d = charger(dossier)
    if not d["baux"]:
        return None
    lignes_banque = []
    if relever:
        try:
            res = banque.releve(dossier, client, aujourd_hui=j)
            for s, err in res["erreurs"].items():
                lignes_banque.append(f"⚠️ Banque {s} : {err}")
        except banque.BanqueNonConfiguree as e:
            return f"Rapprochement des loyers impossible : {e}"
    for c in banque.resume_connexions(dossier, j):
        if c["jours_restants"] is not None and c["jours_restants"] <= 15:
            lignes_banque.append(f"⚠️ L'accès bancaire de {c['societe']} expire le {jj(c['valable_jusqu'])} : "
                                 "reconnectez-le dans le panneau (carte Banque), cela prend une minute.")
    rap = rapprocher(d, banque.operations(dossier), j)
    faites = _lire(Path(dossier) / RELANCES, {})
    actions, a_valider, manuelles = [], [], []
    suspendues = []
    for bid, e in rap["baux"].items():
        impayees = [x for x in e["echeances"] if x["reste"] > SEUIL]
        if not impayees:
            continue
        x = max(impayees, key=lambda y: y["retard"])  # la plus ancienne commande le palier
        palier = _palier(x["retard"])
        cle = f"{bid}|{x['mois']}|{palier}"
        if not palier or cle in faites:
            continue
        if e["bloque"]:  # signalé une fois par palier, puis on attend que le gestionnaire tranche
            if cle + "|suspendu" not in faites:
                faites[cle + "|suspendu"] = {"le": j.isoformat()}
                suspendues.append(f"• {e['bail']['bien']} ({', '.join(e['bail']['locataires'])}) : {NOMS_PALIERS[palier]} "
                                  f"suspendu, {e['bloque']}. Dites à quel bail il revient, ou « ignore <ref> ».")
            continue
        if palier == "mise_en_demeure":
            (Path(dossier) / COURRIERS).mkdir(exist_ok=True)
            f = Path(dossier) / COURRIERS / f"mise-en-demeure_{bid}_{x['mois']}.txt"
            f.write_text(courrier_mise_en_demeure(d, e, j), encoding="utf-8")
            faites[cle] = {"le": j.isoformat(), "statut": "à valider", "courrier": str(f)}
            garantie = f" Garantie : {e['bail']['garantie']}, déclaration à faire." if e["bail"].get("garantie") else ""
            a_valider.append(f"• {e['bail']['bien']} ({', '.join(e['bail']['locataires'])}) : {euros(e['solde'])} dus, "
                             f"{x['retard']} jours de retard. Mise en demeure prête : {f.name}.{garantie} "
                             f"Pour l'envoyer : « envoie la mise en demeure {bid} {x['mois']} ».")
            continue
        sujet, texte = texte_relance(d, e, x, palier)
        if d["reglages"]["auto"] and e["bail"]["emails"]:
            try:
                _envoyer_mail(d, envoyer, ", ".join(e["bail"]["emails"]), sujet, texte)
                faites[cle] = {"le": j.isoformat(), "statut": "envoyé"}
                actions.append(f"• {NOMS_PALIERS[palier].capitalize()} envoyé à {', '.join(e['bail']['locataires'])} "
                               f"({e['bail']['bien']}) : {euros(e['solde'])} dus, {x['retard']} jours de retard.")
                continue
            except Exception as err:
                manuelles.append(f"• {e['bail']['bien']} : {NOMS_PALIERS[palier]} non envoyé ({err}).")
                continue
        faites[cle] = {"le": j.isoformat(), "statut": "préparé"}
        raison = "pas d'adresse mail" if not e["bail"]["emails"] else "mode automatique non activé"
        manuelles.append(f"• {e['bail']['bien']} ({', '.join(e['bail']['locataires'])}) : {NOMS_PALIERS[palier]} à faire "
                         f"({raison}), {euros(e['solde'])} dus, {x['retard']} jours de retard.\n  Objet : {sujet}\n  "
                         + texte.replace("\n", "\n  "))
    _ecrire(Path(dossier) / RELANCES, faites)
    complet = point_complet if point_complet is not None else j.day == int(d["reglages"]["jour_rapport"])
    if not (actions or a_valider or manuelles or suspendues or lignes_banque or complet):
        return None
    morceaux = ["Rapprochement des loyers du " + j.strftime("%d/%m/%Y")]
    if complet:
        morceaux.append(point(rap))
    for titre, liste in (("Relances envoyées", actions), ("Mises en demeure à valider", a_valider),
                         ("Relances à faire à la main", manuelles), ("Relances suspendues", suspendues),
                         ("Banque", lignes_banque)):
        if liste:
            morceaux.append(f"{titre} :\n" + "\n".join(liste))
    return "\n\n".join(morceaux)


def point(rap: dict[str, Any]) -> str:
    """Tableau payé / partiel / impayé de chaque bail, puis virements non identifiés."""
    lignes = []
    for e in sorted(rap["baux"].values(), key=lambda e: (e["bail"]["societe"], e["bail"]["bien"])):
        b, impayees = e["bail"], [x for x in e["echeances"] if x["reste"] > SEUIL]
        if not e["echeances"]:
            statut = "aucune échéance due"
        elif not impayees:
            statut = "✅ à jour" + (f" (avance {euros(e['avance'])})" if e["avance"] > SEUIL else "")
        else:
            x = impayees[0]
            statut = (f"{'🟠 partiel' if any(y['paye'] > 0 for y in impayees) else '🔴 impayé'} : {euros(e['solde'])} dus "
                      f"depuis le {jj(x['date'])} ({x['retard']} j)")
        if e["bloque"]:
            statut += f" ⚠️ {e['bloque']}"
        dernier = max(e["paiements"], key=lambda p: p["date"], default=None)
        recu = f" ; dernier virement {euros(dernier['montant'])} le {jj(dernier['date'])}" if dernier else ""
        lignes.append(f"• {b['societe']} · {b['bien']} ({', '.join(b['locataires'])}) : {statut}{recu}")
    sortie = "Point des loyers :\n" + "\n".join(lignes)
    if rap["inconnus"] or rap["a_repartir"]:
        sortie += "\n\nVirements reçus non rattachés (dites « associe <ref> au bail <id> » ou « ignore <ref> ») :\n" + "\n".join(
            f"• {o['societe']} {jj(o['date'])} {euros(o['montant'])} « {o['payeur'] or o['libelle'][:60]} » [ref {o['ref']}]"
            + (f" (baux possibles : {', '.join(o['baux'])})" if o.get("baux") else "")
            for o in rap["inconnus"] + rap["a_repartir"])
    return sortie


def etat_actuel(dossier: Path, aujourd_hui: date | None = None) -> str:
    d = charger(dossier)
    if not d["baux"]:
        return "Aucun bail suivi : enregistrez-les d'abord (enregistrer_bail)."
    return point(rapprocher(d, banque.operations(dossier), aujourd_hui or date.today()))


def envoyer_mise_en_demeure(dossier: Path, bail_id: str, mois: str, envoyer: Callable[[str, str, dict], str] | None) -> str:
    """Après confirmation du gestionnaire : envoie par mail la mise en demeure préparée (le recommandé papier reste à poster)."""
    faites = _lire(Path(dossier) / RELANCES, {})
    cle = f"{bail_id}|{mois}|mise_en_demeure"
    r = faites.get(cle)
    if not r:
        return "Aucune mise en demeure préparée pour ce bail et ce mois."
    d = charger(dossier)
    bail = next((b for b in d["baux"] if b["id"] == bail_id), None)
    if not bail or not bail["emails"]:
        return "Pas d'adresse mail pour ce bail : le courrier est à envoyer en recommandé papier : " + r["courrier"]
    texte = Path(r["courrier"]).read_text(encoding="utf-8")
    _envoyer_mail(d, envoyer, ", ".join(bail["emails"]), f"Mise en demeure de payer : {bail['bien']}", texte)
    r.update(statut="envoyé", envoye_le=date.today().isoformat())
    _ecrire(Path(dossier) / RELANCES, faites)
    return ("Mise en demeure envoyée par mail. Pour qu'elle produise ses effets, envoyez aussi le courrier en recommandé "
            f"avec accusé de réception : {r['courrier']}")
