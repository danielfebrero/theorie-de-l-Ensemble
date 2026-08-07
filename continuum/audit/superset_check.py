#!/usr/bin/env python3
"""Contrôleur de sur-ensemble strict du Document Opérationnel Maître.

Vérifie qu'une nouvelle version de `master.yaml` n'a RIEN retiré ni modifié de la version
de référence : seules des additions sont permises. C'est la garantie machine de la règle
« sans en changer les bases » — elle remplace l'argument par une preuve reproductible.

Usage :
    python3 continuum/audit/superset_check.py [ref_git] [chemin_candidat] [chemin_reference]

Défauts : ref_git = 636a061 (v0.5.0 canonique), candidat = master.yaml, référence = master.yaml.
Le chemin de référence est indépendant du candidat, ce qui permet de contrôler un fichier
de travail ou un brouillon absent du commit de référence.
Code de sortie : 0 si le sur-ensemble tient, 1 sinon.
"""
import subprocess
import sys

import yaml

# Métadonnées de version : les seules valeurs existantes autorisées à changer.
# Toute autre modification est un échec — y compris une simple reformulation.
ALLOW_CHANGE = {
    "master_document.version",
    "master_document.status",
    "master_document.scope",
    "master_document.activated_proposal",
    "master_document.activated_at",
    "master_document.activated_by",
}

# Bases intouchables : égalité profonde exigée, longueur comprise.
# Ajouter une couche, retirer une capsule ou repondérer une pile échoue ici.
FROZEN_EXACT = {
    "master_document.hierarchy.order",
    "master_document.hierarchy.weights",
    "master_document.decision_stack_by_regime.fuzzy",
    "master_document.decision_stack_by_regime.quantifiable",
    "master_document.decision_stack_proportions_deprecated_v040",
    "master_document.authorship",
    "master_document.active_capsules",
    "master_document.pure_capsules_emitted",
    "master_document.emergency_path",
    "master_document.continuum_locations",
    "master_document.principle",
}


def load_ref(ref, path):
    blob = subprocess.run(
        ["git", "show", f"{ref}:{path}"], capture_output=True, text=True, check=True
    ).stdout
    return yaml.safe_load(blob)


def is_subsequence(base, new):
    """Tout élément de base doit rester présent dans new, dans le même ordre relatif."""
    it = iter(new)
    return all(any(x == y for y in it) for x in base)


def walk(base, new, path, failures, additions):
    if path in ALLOW_CHANGE:
        return
    if path in FROZEN_EXACT:
        if base != new:
            failures.append(f"{path} : base gelée modifiée\n    avant : {base!r}\n    après : {new!r}")
        return

    if isinstance(base, dict):
        if not isinstance(new, dict):
            failures.append(f"{path} : type changé (dict → {type(new).__name__})")
            return
        for k, v in base.items():
            sub = f"{path}.{k}" if path else k
            if k not in new:
                failures.append(f"{sub} : clé SUPPRIMÉE")
            else:
                walk(v, new[k], sub, failures, additions)
        for k in new:
            if k not in base:
                additions.append(f"{path}.{k}" if path else k)
        return

    if isinstance(base, list):
        if not isinstance(new, list):
            failures.append(f"{path} : type changé (list → {type(new).__name__})")
            return
        if not is_subsequence(base, new):
            missing = [x for x in base if x not in new]
            failures.append(
                f"{path} : éléments retirés ou réordonnés"
                + (f"\n    manquants : {missing!r}" if missing else "")
            )
        elif len(new) > len(base):
            additions.append(f"{path}[+{len(new) - len(base)}]")
        return

    if base != new:
        failures.append(f"{path} : valeur modifiée\n    avant : {base!r}\n    après : {new!r}")


def main():
    ref = sys.argv[1] if len(sys.argv) > 1 else "636a061"
    path = sys.argv[2] if len(sys.argv) > 2 else "master.yaml"
    ref_path = sys.argv[3] if len(sys.argv) > 3 else "master.yaml"

    base = load_ref(ref, ref_path)
    with open(path) as f:
        new = yaml.safe_load(f)

    failures, additions = [], []
    walk(base, new, "", failures, additions)

    ref_v = base["master_document"]["version"]
    new_v = new["master_document"]["version"]
    print(f"Référence : {ref}:{ref_path} (v{ref_v})")
    print(f"Candidat  : {path} (v{new_v})")
    print(f"Bases gelées vérifiées : {len(FROZEN_EXACT)}")
    print()

    if additions:
        print(f"ADDITIONS ({len(additions)}) — autorisées :")
        for a in sorted(additions):
            print(f"  + {a}")
        print()

    if failures:
        print(f"ÉCHEC — {len(failures)} violation(s) du sur-ensemble strict :")
        for f_ in failures:
            print(f"  ✗ {f_}")
        return 1

    print("CONFORME — sur-ensemble strict vérifié.")
    print("Aucune valeur existante modifiée, aucune clé supprimée, aucune base repondérée.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
