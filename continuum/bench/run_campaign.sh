#!/usr/bin/env bash
# Campagne complète M3C3-bench : tous les scénarios × trois bras × N réplicats.
#
# Idempotent : une cellule déjà produite et exploitable n'est pas rejouée. On
# peut donc relancer le script pour combler les trous laissés par un refus ou
# une coupure, sans réexécuter ni écraser ce qui a déjà été mesuré.
#
# Le sujet tourne depuis un répertoire neutre, sans dépôt attaché et sans outils.
# L'aveuglement du bras A vient de l'absence de matière, pas de la rédaction de
# l'invite ; les trois bras partagent le même mécanisme et le même modèle, sinon
# la comparaison mesurerait le harnais.
set -uo pipefail

REPO=/home/user/theorie-de-l-Ensemble
OUT=${OUT:-/tmp/bench-campaign}
MODEL=${MODEL:-claude-opus-5}
REPLICATES=${REPLICATES:-5}
WORKERS=${WORKERS:-16}

mkdir -p "$OUT/responses" "$OUT/work"

run_cell() {
  local scenario="$1" arm="$2" rep="$3"
  local prompt_file="$OUT/prompts/$scenario.txt"
  local target="$OUT/responses/$scenario.$arm.r$rep.txt"
  local meta="${target%.txt}.meta"

  # Reprise : une sortie exploitable existante n'est jamais rejouée. Le filtre
  # doit couvrir TOUS les messages du harnais, pas seulement les erreurs d'API :
  # un « session limit » accepté ici deviendrait un essai scoré à zéro qui
  # remplirait la grille sans qu'aucune réponse ait été produite.
  if [[ -s "$target" ]] \
     && ! grep -qiE "API Error|session limit|usage limit|rate limit|no stdin data received" "$target" \
     && [[ $(wc -c < "$target") -ge 200 ]]; then
    printf 'skip   %-34s %-12s r%s\n' "$scenario" "$arm" "$rep"
    return 0
  fi

  local neutral started ended rc
  neutral=$(mktemp -d "$OUT/work/cell-XXXXXX")
  started=$(date -u +%s)
  case "$arm" in
    A_placebo)
      ( cd "$neutral" && claude -p "$(cat "$prompt_file")" \
          --model "$MODEL" --disable-slash-commands --allowedTools "" ) > "$target" 2>&1
      ;;
    B_adapter)
      ( cd "$neutral" && claude -p "$(cat "$prompt_file")" \
          --model "$MODEL" --disable-slash-commands --allowedTools "" \
          --append-system-prompt "$(cat "$REPO/CLAUDE.md")" ) > "$target" 2>&1
      ;;
    D2_candidate)
      # L'en-tête de commentaires est retiré : un corps qui se déclare candidat
      # s'invoque mal comme verrou (mesuré en v2.2) ; la vérité de dépôt reste
      # dans le fichier, la transformation est déclarée dans arms.yaml.
      ( cd "$neutral" && claude -p "Document de référence master.yaml (autorité opérationnelle) :

$(grep -v '^#' "$REPO/continuum/weights/proposal/bench_informed_v2_3_0-candidate.yaml")

---

$(cat "$prompt_file")" \
          --model "$MODEL" --disable-slash-commands --allowedTools "" \
          --append-system-prompt "$(cat "$REPO/CLAUDE.md")" ) > "$target" 2>&1
      ;;
    D_candidate)
      ( cd "$neutral" && claude -p "Document de référence master.yaml (autorité opérationnelle) :

$(cat "$REPO/continuum/weights/proposal/bench_informed_v2_2_0-candidate.yaml")

---

$(cat "$prompt_file")" \
          --model "$MODEL" --disable-slash-commands --allowedTools "" \
          --append-system-prompt "$(cat "$REPO/CLAUDE.md")" ) > "$target" 2>&1
      ;;
    C_canonical)
      ( cd "$neutral" && claude -p "Document de référence master.yaml (autorité opérationnelle) :

$(cat "$REPO/master.yaml")

---

$(cat "$prompt_file")" \
          --model "$MODEL" --disable-slash-commands --allowedTools "" \
          --append-system-prompt "$(cat "$REPO/CLAUDE.md")" ) > "$target" 2>&1
      ;;
  esac
  rc=$?
  ended=$(date -u +%s)
  rm -rf "$neutral"
  printf 'latency_ms=%s\nexit=%s\n' "$(( (ended - started) * 1000 ))" "$rc" > "$meta"

  local status=ok
  grep -qiE "API Error|session limit|usage limit|rate limit" "$target" && status=refus
  [[ $(wc -c < "$target") -lt 200 ]] && status=court
  [[ -s "$target" ]] || status=vide
  printf '%-6s %-34s %-12s r%s  %4ss  %6s o\n' \
    "$status" "$scenario" "$arm" "$rep" "$((ended - started))" "$(wc -c < "$target")"
}
export -f run_cell
export REPO OUT MODEL

mkdir -p "$OUT/prompts"
python3 - "$OUT/prompts" <<'PY'
import sys, pathlib
sys.path.insert(0, "/home/user/theorie-de-l-Ensemble/continuum/bench")
import validate as v
target = pathlib.Path(sys.argv[1])
scenarios, errors = v.load_scenarios()
if errors:
    raise SystemExit(f"registre invalide : {errors}")
# Un scénario remplacé est retiré : le rejouer dépenserait du temps de campagne
# pour des cellules que l'agrégat n'exige plus.
retired = v.superseded_ids(scenarios, "scenario_id")
scenarios = [s for s in scenarios if s["scenario_id"] not in retired]
for scenario in scenarios:
    (target / f"{scenario['scenario_id']}.txt").write_text(scenario["task"]["prompt"], encoding="utf-8")
print(f"{len(scenarios)} énoncé(s) extraits")
PY

mapfile -t SCENARIOS < <(ls "$OUT/prompts" | sed 's/\.txt$//' | sort)
ARMS=(A_placebo B_adapter C_canonical D_candidate D2_candidate)

total=$(( ${#SCENARIOS[@]} * ${#ARMS[@]} * REPLICATES ))
echo "cellules : $total  ·  workers : $WORKERS  ·  modèle : $MODEL"
echo

for scenario in "${SCENARIOS[@]}"; do
  for arm in "${ARMS[@]}"; do
    for rep in $(seq 1 "$REPLICATES"); do
      echo "$scenario $arm $rep"
    done
  done
done | xargs -P "$WORKERS" -n 3 bash -c 'run_cell "$0" "$1" "$2"'

echo
echo "=== bilan ==="
ok=$(grep -Lq "API Error" "$OUT"/responses/*.txt 2>/dev/null | wc -l)
echo "sorties : $(ls "$OUT"/responses/*.txt 2>/dev/null | wc -l) / $total"
echo "refus   : $(grep -l "API Error" "$OUT"/responses/*.txt 2>/dev/null | wc -l)"
