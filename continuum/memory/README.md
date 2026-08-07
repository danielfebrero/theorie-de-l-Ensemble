# Continuum memory (v2.0.0 release candidate)

Mémoire opérationnelle versionnée du dépôt M3C3. La mémoire n'est ni le
contexte de conversation, ni une modification implicite des poids : seuls les
artefacts déclarés ici, validés contre [`schema-v2.yaml`](schema-v2.yaml) et
reliés à une preuve peuvent être présentés comme mémoire Continuum.

| Chemin | Rôle |
|---|---|
| [`parameters/`](parameters/) | Snapshot des paramètres à conserver (piles, auxiliaires, constantes) |
| [`patterns/`](patterns/) | Index des patterns de décision (audit-backed) |
| [`creator/`](creator/) | Index du créateur / émetteur / authorship |
| [`index.yaml`](index.yaml) | Index machine-readable, hashes SHA-256, base Git et politique de promotion/rollback |
| [`schema-v2.yaml`](schema-v2.yaml) | Contrat minimal des entrées de mémoire v2 |

Chaque artefact est adressé par contenu et le validateur refuse tout YAML non
indexé. Les fichiers déjà présents à `history_base` doivent rester identiques ;
chaque révision ultérieure crée un nouveau chemin. Une correction utilise
`supersedes`; elle ne réécrit pas l'historique. Les statuts `candidate`,
`active`, `active_with_known_limitations`, `rolled_back` et `deprecated` sont
distincts de la force des preuves.

La classe de source `provider_attested` est réservée et refusée tant qu'aucun
vérificateur d'identité/attestation n'est configuré. Un nom, un chemin et un
hash auto-déclarés ne constituent pas une attestation fournisseur.

`history_base` est épinglé au premier commit v2 contenant ces artefacts :
`188f0bc517822e95cccc4ba1baaef9f11bc32b2c`. Le validateur exige la même ancre
dans `master.yaml`, puis compare octet pour octet tous les artefacts déjà
présents à cette base. Un fichier absent de la base reste explicitement une
addition candidate jusqu'à une ancre ultérieure.

Voir `master.yaml` → `continuum_memory`, `activation_policy` et
`weight_integration_contract`.
