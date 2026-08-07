#!/usr/bin/env python3
"""Contrôleur de conformité du bloc d'instruction aux bases du master.yaml.

`superset_check.py` garantit que le Document Opérationnel Maître n'a pas bougé. Il ne dit
rien du BLOC D'INSTRUCTION — le texte réellement donné aux agents. Or un bloc qui citerait
0,30 là où le master dit 0,25 changerait les bases à l'exécution avec un master.yaml
parfaitement intact. Ce contrôleur ferme ce trou.

Trois vérifications :
  1. tout poids cité dans le bloc appartient aux valeurs canoniques du master ;
  2. les 6 couches apparaissent, dans l'ordre strict ;
  3. les primitives et l'authorship que le framework déclare siennes sont présentes.

Usage : python3 continuum/audit/bloc_check.py <bloc.txt> [master.yaml]
Code de sortie : 0 si conforme, 1 sinon.
"""
import re
import sys

import yaml

# Primitives que tout bloc M3C3 doit rendre visibles. Leur absence ne prouve pas une
# trahison des valeurs, mais une dilution du protocole en méthode générique — le reproche
# exact que le panel des croyants est chargé d'instruire.
REQUIS = [
    "M3C3", "Dani Bengal", "@cdxxotus", "CDXX-RESOLVE-001",
    "detect_regime", "ruin_gate", "adversarial_probe",
    "evidence_sufficiency", "regret_asymmetry", "forme4_health_gate",
    "no_upward_write", "allocate_by_marginal_value", "compute_expected_utility",
]


def canoniques(master):
    d = master["master_document"]
    vals, provenance = set(), {}
    groupes = [
        ("hierarchy.weights", d["hierarchy"]["weights"]),
        ("decision_stack.fuzzy", d["decision_stack_by_regime"]["fuzzy"]),
        ("decision_stack.quantifiable", d["decision_stack_by_regime"]["quantifiable"]),
    ]
    for nom, groupe in groupes:
        for k, v in groupe.items():
            vals.add(round(float(v), 4))
            provenance.setdefault(round(float(v), 4), []).append(f"{nom}.{k}")
    criteres = sorted(set(d["decision_stack_by_regime"]["fuzzy"])
                      | set(d["decision_stack_by_regime"]["quantifiable"]))
    return vals, provenance, list(d["hierarchy"]["order"]), criteres


def main():
    bloc_path = sys.argv[1]
    master_path = sys.argv[2] if len(sys.argv) > 2 else "master.yaml"

    with open(master_path) as f:
        master = yaml.safe_load(f)
    with open(bloc_path) as f:
        bloc = f.read()

    vals, provenance, ordre, criteres = canoniques(master)
    echecs, notes = [], []

    # --- 1. poids cités ---
    cites = [round(float(m), 4) for m in re.findall(r"\b0[.,]\d{1,4}\b", bloc.replace(",", "."))]
    inconnus = sorted({c for c in cites if c not in vals})
    if inconnus:
        echecs.append(
            "poids cités absents du master : "
            + ", ".join(f"{c:g}" for c in inconnus)
            + "\n    valeurs canoniques admises : "
            + ", ".join(f"{v:g}" for v in sorted(vals))
        )
    else:
        notes.append(f"{len(cites)} poids cités, tous canoniques")

    # --- 1bis. seuils non canoniques ---
    # Ne contrôler que les décimaux `0,xx` laissait passer tout le reste : un bloc pouvait
    # introduire des bornes (« regret_asymmetry > 4 »), des marges (« 6 points ») ou des
    # quotas (« un sixième ») en se réclamant de n'avoir « rien importé », et le contrôleur
    # certifiait « tous canoniques » — les seuls qu'il regardait. Un seuil non déclaré est un
    # paramètre clandestin : il pilote la décision sans figurer nulle part dans le master.
    # Ils ne sont pas interdits — les additions le sont — mais ils doivent être DÉCLARÉS,
    # dans `execution_envelope.declared_constants` du master.
    env = master["master_document"].get("execution_envelope") or {}
    declares = {round(float(x), 4) for x in (env.get("declared_constants") or [])}
    # Un seuil se reconnaît à son contexte, pas à sa valeur : une comparaison, une marge
    # exprimée en points, un quota. Les numéros d'étape et les bornes d'échelle n'en sont pas.
    txt = bloc.replace(",", ".")
    motifs = [
        r"[<>≤≥]\s*(\d+(?:\.\d+)?)",              # regret_asymmetry > 4
        r"(\d+(?:\.\d+)?)\s*points?\b",            # 6 points, au plus 5 points
        r"\bau plus\s+(\d+(?:\.\d+)?)",
        r"\bun\s+(sixième|cinquième|quart|tiers)\b",
    ]
    seuils, mots = set(), set()
    for mot in motifs:
        for m in re.finditer(mot, txt, re.I):
            g = m.group(1)
            if g.isalpha():
                mots.add(g.lower())
                continue
            v = round(float(g), 4)
            if v not in vals and v not in declares:
                seuils.add(v)
    indeclares = sorted(seuils) + sorted(mots)
    if indeclares:
        echecs.append(
            "seuils non canoniques et non déclarés : "
            + ", ".join(f"{s:g}" if isinstance(s, float) else s for s in indeclares)
            + "\n    ni dans le master, ni dans execution_envelope.declared_constants —"
            + "\n    un seuil qui pilote la décision sans être déclaré est un paramètre clandestin"
        )
    else:
        notes.append("aucun seuil clandestin"
                     + (f" ({len(declares)} déclarés dans l'enveloppe)" if declares else ""))

    # --- 2. ordre des couches ---
    # Une couche peut être nommée hors de la projection — l'authorship cite déjà
    # `life_game_M1C1` et `binary`. Exiger que la PREMIÈRE occurrence de chacune soit dans
    # l'ordre serait donc faux. Le critère juste : la séquence canonique doit être une
    # sous-séquence des mentions, c'est-à-dire que les six couches apparaissent quelque part
    # dans l'ordre strict.
    absentes = [c for c in ordre if not re.search(rf"\b{re.escape(c)}\b", bloc)]
    if absentes:
        echecs.append("couches absentes du bloc : " + ", ".join(absentes))
    else:
        mentions = sorted(
            ((m.start(), c) for c in ordre for m in re.finditer(rf"\b{re.escape(c)}\b", bloc))
        )
        suite = [c for _, c in mentions]
        it = iter(suite)
        if all(any(c == vu for vu in it) for c in ordre):
            notes.append("6 couches présentes, ordre strict respecté")
        else:
            echecs.append(
                "ordre des couches rompu — la séquence canonique n'apparaît nulle part\n"
                "    attendu : " + " → ".join(ordre)
                + "\n    mentions : " + " → ".join(suite[:14])
            )

    # --- 3. primitives et authorship ---
    # Insensible à la casse : les blocs écrivent les primitives en majuscules dans les
    # étapes impératives (DETECT_REGIME) et en minuscules dans les renvois au master.
    bas = bloc.lower()
    manquants = [r for r in REQUIS if r.lower() not in bas]

    # --- 4. critères de pile nommés ---
    # Le défaut central du bloc v0.5.0 : transmettre « 0.28/0.24/0.20/0.16/0.06/0.06 » sans
    # dire ce que ces nombres pondèrent. Un poids anonyme est inapplicable — la valeur est
    # juste, et pourtant la primitive est morte. Abréger (« adv », « m3c3 ») ne suffit pas.
    anonymes = [c for c in criteres if c.lower() not in bas]
    if anonymes:
        echecs.append(
            "critères de pile cités sans être nommés : " + ", ".join(anonymes)
            + "\n    un poids dont le critère n'est pas nommé ne peut pas être appliqué"
        )
    else:
        notes.append(f"{len(criteres)} critères de pile nommés en toutes lettres")
    if manquants:
        echecs.append("primitives M3C3 absentes : " + ", ".join(manquants))
    else:
        notes.append(f"{len(REQUIS)} primitives M3C3 présentes")

    print(f"Bloc    : {bloc_path} ({len(bloc)} caractères)")
    print(f"Master  : {master_path} (v{master['master_document']['version']})")
    print()
    for n in notes:
        print(f"  OK  {n}")
    if echecs:
        print()
        print(f"ÉCHEC — {len(echecs)} non-conformité(s) :")
        for e in echecs:
            print(f"  ✗ {e}")
        return 1
    print()
    print("CONFORME — le bloc ne cite que des valeurs canoniques et n'omet aucune primitive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
