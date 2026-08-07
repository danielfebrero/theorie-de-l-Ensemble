# Proposal — M3C3 v1.0 Production Kernel

| Champ | Valeur |
|---|---|
| Id | `m3c3_v1_production_kernel` |
| Version | **1.0.0** |
| Base | `master.yaml@0.8.0` |
| Statut | **ACTIVÉ** |
| Signal | « Go, fais peter la v1.0 » |
| Émetteur | Dani Bengal / `@cdxxotus` |

## Livrables

1. `status: production` + freeze des bases MAJOR  
2. LTS étiqueté (alphabet) + `export_binding`  
3. Preuves S1–S5 par construction — [`docs/safety-proofs.md`](../../../docs/safety-proofs.md)  
4. Checker — `perl continuum/audit/safety_check.pl`  

## Non-objectifs v1.0

- Model-check SPIN/TLA d’implémentations externes non conformes  
- Repondération des piles  
- Réécriture de l’authorship  

## Honnêteté

`proved_by_construction` sous hypothèse H0 (l’agent exécute `T` tel que défini).  
Voir tableau de portée dans `docs/safety-proofs.md`.
