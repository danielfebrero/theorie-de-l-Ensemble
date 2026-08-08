#!/usr/bin/env bash
# Dispatcher générique de tâches d'écriture sur des workers CLI parallèles.
#
# Chaque tâche est un fichier d'invite dans $IN ; sa sortie va dans $OUT sous le
# même nom. Le travail est saturé en attente réseau, pas en CPU : le nombre de
# workers n'est donc pas borné par le nombre de cœurs.
#
# Idempotent : une sortie déjà présente et non vide n'est pas rejouée, ce qui
# permet de relancer pour combler les échecs sans refaire ce qui a abouti.
#
# Ces workers ne sont PAS des sujets de bench : ils tournent dans le dépôt, avec
# outils de lecture, et voient donc CLAUDE.md. C'est voulu — ce sont des auteurs,
# pas des mesurés. Ne jamais réutiliser ce script pour produire un essai.
set -uo pipefail

REPO=${REPO:-/home/user/theorie-de-l-Ensemble}
IN=${IN:?répertoire des invites requis}
OUT=${OUT:?répertoire des sorties requis}
MODEL=${MODEL:-claude-opus-5}
WORKERS=${WORKERS:-24}
TOOLS=${TOOLS:-"Read Grep Glob Bash"}

mkdir -p "$OUT"

run_task() {
  local prompt_file="$1"
  local id target started ended
  id=$(basename "$prompt_file" .txt)
  target="$OUT/$id.out"

  if [[ -s "$target" ]] && ! grep -q "API Error" "$target"; then
    printf 'skip   %s\n' "$id"
    return 0
  fi

  started=$(date -u +%s)
  ( cd "$REPO" && claude -p "$(cat "$prompt_file")" \
      --model "$MODEL" --allowedTools $TOOLS ) > "$target" 2>&1
  ended=$(date -u +%s)

  local status=ok
  grep -q "API Error" "$target" && status=erreur
  [[ -s "$target" ]] || status=vide
  printf '%-7s %-44s %4ss  %6s o\n' "$status" "$id" "$((ended - started))" "$(wc -c < "$target")"
}
export -f run_task
export REPO OUT MODEL TOOLS

count=$(ls "$IN"/*.txt 2>/dev/null | wc -l)
echo "tâches : $count  ·  workers : $WORKERS  ·  modèle : $MODEL"
echo

ls "$IN"/*.txt | xargs -P "$WORKERS" -n 1 bash -c 'run_task "$0"'

echo
echo "=== bilan ==="
echo "sorties : $(ls "$OUT"/*.out 2>/dev/null | wc -l) / $count"
echo "erreurs : $(grep -l 'API Error' "$OUT"/*.out 2>/dev/null | wc -l)"
