#!/usr/bin/env bash
# Harnais du pilote M3C3-bench.
#
# Le sujet tourne depuis un répertoire neutre, sans dépôt attaché et sans outils :
# l'aveuglement du bras A vient de l'absence de matière, pas de la rédaction de
# l'invite. Les trois bras partagent le même mécanisme et le même modèle ; seule
# la matière M3C3 injectée change, sinon la comparaison mesurerait le harnais.
set -uo pipefail

REPO=/home/user/theorie-de-l-Ensemble
OUT=/tmp/bench-subject/results
WORK=/tmp/bench-subject/run
MODEL=claude-opus-5

mkdir -p "$OUT" "$WORK"

run_cell() {
  local scenario="$1" arm="$2"
  local prompt_file="$OUT/$scenario.prompt.txt"
  local target="$OUT/$scenario.$arm.txt"
  local meta="$OUT/$scenario.$arm.meta"
  local started ended

  started=$(date -u +%s)
  case "$arm" in
    A_placebo)
      ( cd "$WORK" && claude -p "$(cat "$prompt_file")" \
          --model "$MODEL" --disable-slash-commands --allowedTools "" ) > "$target" 2>&1
      ;;
    B_adapter)
      ( cd "$WORK" && claude -p "$(cat "$prompt_file")" \
          --model "$MODEL" --disable-slash-commands --allowedTools "" \
          --append-system-prompt "$(cat "$REPO/CLAUDE.md")" ) > "$target" 2>&1
      ;;
    C_canonical)
      ( cd "$WORK" && claude -p "Document de référence master.yaml (autorité opérationnelle) :

$(cat "$REPO/master.yaml")

---

$(cat "$prompt_file")" \
          --model "$MODEL" --disable-slash-commands --allowedTools "" \
          --append-system-prompt "$(cat "$REPO/CLAUDE.md")" ) > "$target" 2>&1
      ;;
  esac
  ended=$(date -u +%s)
  printf 'latency_ms=%s\n' "$(( (ended - started) * 1000 ))" > "$meta"
  printf '%-34s %-12s %6s octets  %3ss\n' "$scenario" "$arm" "$(wc -c < "$target")" "$((ended - started))"
}

export -f run_cell
export REPO OUT WORK MODEL

SCENARIOS=(membrane-a0-trap-v1 export-mandatory-fields-v1 ruin-sustainable-variance-v1)
ARMS=(A_placebo B_adapter C_canonical)

for scenario in "${SCENARIOS[@]}"; do
  python3 - "$scenario" <<'PY'
import sys, pathlib
sys.path.insert(0, "/home/user/theorie-de-l-Ensemble/continuum/bench")
import validate as v
name = sys.argv[1]
sc = v.load_path(f"/home/user/theorie-de-l-Ensemble/continuum/bench/scenarios/{name}.yaml")
pathlib.Path(f"/tmp/bench-subject/results/{name}.prompt.txt").write_text(sc["task"]["prompt"], encoding="utf-8")
PY
done

# Trois cellules en vol à la fois : assez pour tenir le budget de temps, assez
# peu pour que chaque sujet reste une exécution indépendante.
for scenario in "${SCENARIOS[@]}"; do
  for arm in "${ARMS[@]}"; do
    echo "$scenario $arm"
  done
done | xargs -P 3 -n 2 bash -c 'run_cell "$0" "$1"'

echo "--- terminé ---"
ls -la "$OUT" | grep -c '\.txt$'
