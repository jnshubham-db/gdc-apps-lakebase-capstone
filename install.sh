#!/usr/bin/env bash
# Capstone installer — Databricks Apps + Lakebase
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/jnshubham/gdc-apps-lakebase-capstone/main/install.sh | bash
#
# Provisions: gold tables, Lakebase instance, AI/BI dashboard, Genie space.
# Notebook 03 (synced + staging tables) is intentionally skipped — that's
# capstone tasks T2-T5, your job.
#
# Installs **nothing** on your machine. Uses what's already there:
# bash, curl, tar, python3 (stdlib only), and the `databricks` CLI.

set -euo pipefail

REPO_OWNER="jnshubham"
REPO_NAME="gdc-apps-lakebase-capstone"
REPO_BRANCH="main"
TARBALL_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/${REPO_BRANCH}.tar.gz"

# ── stdin handling for `curl | bash` ─────────────────────────────────────────
if [[ -t 0 ]]; then TTY=/dev/stdin; else TTY=/dev/tty; fi

# ── colors / glyphs ───────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    RESET=$'\e[0m'; BOLD=$'\e[1m'; DIM=$'\e[2m'
    FG_CYAN=$'\e[36m'; FG_GREEN=$'\e[32m'; FG_RED=$'\e[31m'
    FG_YELLOW=$'\e[33m'; FG_BLUE=$'\e[34m'; FG_MAGENTA=$'\e[35m'
    FG_GREY=$'\e[90m'
else
    RESET=""; BOLD=""; DIM=""
    FG_CYAN=""; FG_GREEN=""; FG_RED=""; FG_YELLOW=""; FG_BLUE=""; FG_MAGENTA=""; FG_GREY=""
fi

CHK="✓"; CROSS="✗"; ARR="▸"; BUL="•"; BOX_H="─"; BOX_TL="╭"; BOX_TR="╮"; BOX_BL="╰"; BOX_BR="╯"; BOX_V="│"

box_top()    { local w=${1:-72}; printf '%s%s%s\n' "$BOX_TL" "$(repeat "$BOX_H" "$w")" "$BOX_TR"; }
box_bottom() { local w=${1:-72}; printf '%s%s%s\n' "$BOX_BL" "$(repeat "$BOX_H" "$w")" "$BOX_BR"; }
repeat()     { local s=$1 n=$2; printf "$s%.0s" $(seq 1 "$n"); }

banner() {
    local text=$1
    local width=72
    local pad=$((width - ${#text} - 2))
    printf "\n%s%s%s\n" "$FG_CYAN$BOLD" "$(box_top "$width")" "$RESET"
    printf "%s%s %s%s%s\n" "$FG_CYAN$BOLD" "$BOX_V" "$text" "$(repeat ' ' "$pad")" "$BOX_V$RESET"
    printf "%s%s%s\n" "$FG_CYAN$BOLD" "$(box_bottom "$width")" "$RESET"
}

step()   { printf "\n%s%s %s%s\n" "$FG_BLUE$BOLD" "$ARR" "$1" "$RESET"; }
substep(){ printf "  %s%s %s%s\n" "$FG_MAGENTA" "$BUL" "$1" "$RESET"; }
info()   { printf "    %s%s%s\n" "$FG_GREY" "$1" "$RESET"; }
ok()     { printf "    %s%s %s%s\n" "$FG_GREEN" "$CHK" "$1" "$RESET"; }
warn()   { printf "    %s%s %s%s\n" "$FG_YELLOW" "!" "$1" "$RESET"; }
fail()   { printf "    %s%s %s%s\n" "$FG_RED" "$CROSS" "$1" "$RESET" 1>&2; }
abort()  { fail "$1"; exit 1; }

# ── tmpdir + cleanup ─────────────────────────────────────────────────────────
TMPDIR=$(mktemp -d -t capstone-XXXXXX)
cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

# ── interactive helpers (stdlib python3, no pip) ─────────────────────────────
write_helpers() {
    cat > "$TMPDIR/_pick.py" <<'PY'
#!/usr/bin/env python3
"""Arrow-key menu picker. stdin: option lines; argv[1]: prompt; argv[2..n]: --header lines."""
import os, sys, tty, termios

def main():
    options = [line.rstrip("\n") for line in sys.stdin.readlines() if line.strip()]
    if not options:
        print("0"); return
    prompt = sys.argv[1] if len(sys.argv) > 1 else ""
    header = sys.argv[2:] if len(sys.argv) > 2 else []
    fd_in  = os.open("/dev/tty", os.O_RDONLY)
    fd_out = os.open("/dev/tty", os.O_WRONLY)
    write = lambda s: os.write(fd_out, s.encode("utf-8"))
    old = termios.tcgetattr(fd_in)
    idx = 0
    try:
        tty.setcbreak(fd_in)
        write("\x1b[?25l")  # hide cursor
        first = True
        while True:
            if not first:
                write(f"\x1b[{len(header) + len(options) + 1}A")  # move cursor up to redraw
            first = False
            for h in header:
                write(f"\x1b[2K\r{h}\r\n")
            write(f"\x1b[2K\r\x1b[1m{prompt}\x1b[0m  \x1b[2m(↑/↓ to move, enter to select, q to quit)\x1b[0m\r\n")
            for i, opt in enumerate(options):
                marker = "\x1b[36m▶\x1b[0m" if i == idx else " "
                style_on  = "\x1b[1;36m" if i == idx else "\x1b[2m"
                style_off = "\x1b[0m"
                write(f"\x1b[2K\r  {marker} {style_on}{opt}{style_off}\r\n")
            ch = os.read(fd_in, 1).decode("utf-8", errors="ignore")
            if ch == "\x1b":
                seq = os.read(fd_in, 2).decode("utf-8", errors="ignore")
                if seq == "[A": idx = (idx - 1) % len(options)
                elif seq == "[B": idx = (idx + 1) % len(options)
            elif ch in ("k", "K"): idx = (idx - 1) % len(options)
            elif ch in ("j", "J"): idx = (idx + 1) % len(options)
            elif ch in ("\r", "\n"): break
            elif ch == "q": idx = -1; break
            elif ch.isdigit():
                # quick-jump: type a digit to pick that index if in range
                n = int(ch)
                if n < len(options):
                    idx = n; break
    finally:
        write("\x1b[?25h")  # show cursor
        termios.tcsetattr(fd_in, termios.TCSADRAIN, old)
    if idx < 0:
        print("CANCELLED", file=sys.stderr); sys.exit(2)
    print(idx)

if __name__ == "__main__":
    main()
PY

    cat > "$TMPDIR/_prompt.py" <<'PY'
#!/usr/bin/env python3
"""Styled text prompt with default + validation hint. argv[1]=label, argv[2]=default."""
import os, sys
label   = sys.argv[1] if len(sys.argv) > 1 else "Input"
default = sys.argv[2] if len(sys.argv) > 2 else ""
fd_in  = os.open("/dev/tty", os.O_RDONLY)
fd_out = os.open("/dev/tty", os.O_WRONLY)
write  = lambda s: os.write(fd_out, s.encode("utf-8"))
hint = f"  \x1b[2m(default: {default})\x1b[0m" if default else ""
write(f"  \x1b[36m▸\x1b[0m \x1b[1m{label}\x1b[0m{hint}\n  \x1b[2m›\x1b[0m ")
buf = b""
while True:
    ch = os.read(fd_in, 1)
    if ch in (b"\r", b"\n"):
        write("\n"); break
    if ch == b"\x7f":  # backspace
        if buf:
            buf = buf[:-1]; write("\x1b[D \x1b[D")
        continue
    if ch == b"\x03":  # Ctrl-C
        write("\n"); sys.exit(130)
    buf += ch
    write(ch.decode("utf-8", errors="ignore"))
val = buf.decode("utf-8").strip() or default
print(val)
PY

    cat > "$TMPDIR/_confirm.py" <<'PY'
#!/usr/bin/env python3
"""Yes/no with default. argv[1]=label, argv[2]=default(y|n)."""
import os, sys
label   = sys.argv[1] if len(sys.argv) > 1 else "OK?"
default = (sys.argv[2] if len(sys.argv) > 2 else "y").lower()
fd_in  = os.open("/dev/tty", os.O_RDONLY)
fd_out = os.open("/dev/tty", os.O_WRONLY)
write  = lambda s: os.write(fd_out, s.encode("utf-8"))
hint = "[Y/n]" if default == "y" else "[y/N]"
write(f"  \x1b[36m▸\x1b[0m \x1b[1m{label}\x1b[0m \x1b[2m{hint}\x1b[0m\n  \x1b[2m›\x1b[0m ")
buf = b""
while True:
    ch = os.read(fd_in, 1)
    if ch in (b"\r", b"\n"):
        write("\n"); break
    if ch == b"\x03":
        write("\n"); sys.exit(130)
    buf += ch
    write(ch.decode("utf-8", errors="ignore"))
val = buf.decode("utf-8").strip().lower() or default
sys.exit(0 if val.startswith("y") else 1)
PY
}
write_helpers

prompt_text() {
    # prompt_text VAR_NAME "Question" "default"
    local _name=$1 _q=$2 _default=${3:-} _val
    _val=$(python3 "$TMPDIR/_prompt.py" "$_q" "$_default")
    printf -v "$_name" '%s' "$_val"
}

prompt_confirm() {
    # returns 0 for yes
    python3 "$TMPDIR/_confirm.py" "$1" "${2:-y}"
}

pick_index() {
    # pick_index "prompt" "header line 1" "header line 2"...  (options on stdin)
    python3 "$TMPDIR/_pick.py" "$@"
}

# ── spinner ──────────────────────────────────────────────────────────────────
SPIN_PID=""
SPIN_TXT=""
spin_start() {
    SPIN_TXT="$1"
    (
        local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
        local i=0
        while true; do
            printf "\r    %s%s%s %s" "$FG_CYAN" "${frames[i]}" "$RESET" "$SPIN_TXT" > /dev/tty 2>/dev/null || true
            i=$(( (i + 1) % ${#frames[@]} ))
            sleep 0.1
        done
    ) &
    SPIN_PID=$!
    disown 2>/dev/null || true
}
spin_msg() {
    SPIN_TXT="$1"
}
spin_stop() {
    local final=${1:-done} status=${2:-ok}
    if [[ -n "$SPIN_PID" ]]; then
        kill "$SPIN_PID" 2>/dev/null || true
        wait "$SPIN_PID" 2>/dev/null || true
        SPIN_PID=""
    fi
    printf "\r\033[2K" > /dev/tty 2>/dev/null || true
    if [[ "$status" == "ok" ]]; then
        printf "    %s%s %s%s\n" "$FG_GREEN" "$CHK" "$final" "$RESET"
    else
        printf "    %s%s %s%s\n" "$FG_RED" "$CROSS" "$final" "$RESET"
    fi
}

# ── 1. preflight ─────────────────────────────────────────────────────────────
banner "Capstone installer  ·  Databricks Apps + Lakebase"
printf "  %sRepo:%s https://github.com/%s/%s\n" "$BOLD" "$RESET" "$REPO_OWNER" "$REPO_NAME"
printf "  Provisions gold tables, Lakebase, AI/BI dashboard, Genie. Notebook 03 is your job (T2-T5).\n"

step "Preflight"
command -v databricks >/dev/null || abort "databricks CLI not found. Install: https://docs.databricks.com/en/dev-tools/cli/install.html"
command -v python3    >/dev/null || abort "python3 not found (needed only for stdlib JSON / prompts)."
command -v curl       >/dev/null || abort "curl not found."
command -v tar        >/dev/null || abort "tar not found."
DB_VER=$(databricks --version | head -1)
PY_VER=$(python3 -c 'import sys;print(sys.version.split()[0])')
ok "$DB_VER  ·  python $PY_VER"

# ── 2. profile + connection ──────────────────────────────────────────────────
step "Connect to Databricks"

# List configured profiles via the CLI; prefer arrow-key picker, fall back to text prompt.
PROFILES_JSON=$(databricks auth profiles -o json 2>/dev/null || echo '{"profiles":[]}')
PROFILE_LINES=$(echo "$PROFILES_JSON" | python3 -c '
import json, sys
data = json.load(sys.stdin)
for p in data.get("profiles", []):
    name  = p.get("name", "?")
    host  = p.get("host", "?")
    cloud = p.get("cloud", "")
    valid = "✓" if p.get("valid") else "✗"
    print(f"{name:<24}  {valid} {host:<60} {cloud}")
')

if [[ -n "$PROFILE_LINES" ]]; then
    PROFILE_PICK=$(echo "$PROFILE_LINES" | pick_index "Select a Databricks CLI profile" "" || true)
    [[ -z "$PROFILE_PICK" || "$PROFILE_PICK" == "CANCELLED" ]] && abort "Cancelled."
    PROFILE=$(echo "$PROFILES_JSON" | python3 -c "import json,sys;print(json.load(sys.stdin)['profiles'][$PROFILE_PICK]['name'])")
    ok "Profile: $PROFILE"
else
    warn "No profiles found in ~/.databrickscfg"
    prompt_text PROFILE "Databricks CLI profile name" "${DATABRICKS_CONFIG_PROFILE:-DEFAULT}"
fi

spin_start "Verifying auth as profile '${PROFILE}'…"
if ! ME_JSON=$(databricks current-user me --profile "$PROFILE" -o json 2>&1); then
    spin_stop "Auth failed for profile '${PROFILE}'" "fail"
    abort "Run: databricks auth login --profile $PROFILE"
fi
USER_NAME=$(echo "$ME_JSON" | python3 -c "import json,sys;print(json.load(sys.stdin).get('userName','?'))")
HOST=$(echo "$PROFILES_JSON" | python3 -c "
import json, sys
target = '$PROFILE'
for p in json.load(sys.stdin).get('profiles', []):
    if p.get('name') == target:
        print((p.get('host') or '').rstrip('/'))
        break
")
spin_stop "Connected as $USER_NAME ($HOST)" "ok"

# ── 3. parameter prompts ─────────────────────────────────────────────────────
step "Capstone settings"
prompt_text CATALOG "Catalog name"        "capstone"
prompt_text SCHEMA  "Schema name"         "gold"

step "Pick a SQL warehouse (arrow keys)"
spin_start "Listing warehouses…"
WH_JSON=$(databricks warehouses list --profile "$PROFILE" -o json)
spin_stop "Loaded warehouses" "ok"

WH_COUNT=$(echo "$WH_JSON" | python3 -c "import json,sys;print(len(json.load(sys.stdin)))")
[[ "$WH_COUNT" == "0" ]] && abort "No SQL warehouses visible to '$PROFILE'."

# Build human-readable lines + a parallel list of IDs / names
WH_LINES=$(echo "$WH_JSON" | python3 -c '
import json, sys
for wh in json.load(sys.stdin):
    n = (wh.get("name") or "?")[:40]
    s = wh.get("state") or "?"
    t = (wh.get("warehouse_type") or "")
    wid = wh.get("id", "?")
    print(f"{n:<40}  state={s:<10}  type={t:<6}  id={wid}")
')
WH_PICK=$(echo "$WH_LINES" | pick_index "Select a SQL warehouse" "" || true)
[[ -z "$WH_PICK" || "$WH_PICK" == "CANCELLED" ]] && abort "Cancelled."
WAREHOUSE_ID=$(echo "$WH_JSON"   | python3 -c "import json,sys;print(json.load(sys.stdin)[$WH_PICK]['id'])")
WAREHOUSE_NAME=$(echo "$WH_JSON" | python3 -c "import json,sys;print(json.load(sys.stdin)[$WH_PICK].get('name','?'))")
ok "Selected: $WAREHOUSE_NAME ($WAREHOUSE_ID)"

step "Lakebase + dashboard settings"
prompt_text INSTANCE_NAME  "Lakebase instance name"           "capstone-pg"

# Capacity uses arrow-key picker (fixed list)
printf "%s\n" "CU_1   (1 vCPU, smallest)" "CU_2" "CU_4" "CU_8" "CU_16" > "$TMPDIR/_cap.txt"
substep "Pick Lakebase capacity"
CAP_PICK=$(pick_index "Lakebase capacity" "" < "$TMPDIR/_cap.txt" || true)
[[ -z "$CAP_PICK" || "$CAP_PICK" == "CANCELLED" ]] && abort "Cancelled."
CAPACITY_OPTIONS=("CU_1" "CU_2" "CU_4" "CU_8" "CU_16")
CAPACITY=${CAPACITY_OPTIONS[$CAP_PICK]}
ok "Capacity: $CAPACITY"

prompt_text UC_LB_CATALOG  "Lakebase UC catalog"              "capstone_lakebase"
prompt_text DB_NAME        "Postgres database name"           "capstone_db"
prompt_text DASHBOARD_NAME "Dashboard display name"           "Customer 360 — Capstone"
prompt_text SPACE_TITLE    "Genie space title"                "Customer 360 — Capstone Genie"
prompt_text PARENT_PATH    "Workspace folder for notebooks"   "/Workspace/Shared/capstone"

# ── confirmation panel ───────────────────────────────────────────────────────
banner "Review"
print_kv() { printf "  %s%-22s%s  %s\n" "$BOLD" "$1" "$RESET" "$2"; }
print_kv "profile"        "$PROFILE"
print_kv "host"           "$HOST"
print_kv "catalog"        "$CATALOG"
print_kv "schema"         "$SCHEMA"
print_kv "warehouse"      "$WAREHOUSE_NAME ($WAREHOUSE_ID)"
print_kv "instance_name"  "$INSTANCE_NAME"
print_kv "capacity"       "$CAPACITY"
print_kv "uc_lb_catalog"  "$UC_LB_CATALOG"
print_kv "database_name"  "$DB_NAME"
print_kv "dashboard_name" "$DASHBOARD_NAME"
print_kv "space_title"    "$SPACE_TITLE"
print_kv "parent_path"    "$PARENT_PATH"
echo
prompt_confirm "Proceed?" "y" || { warn "Aborted by user."; exit 0; }

# ── 4. download repo bundle ──────────────────────────────────────────────────
step "Download installer bundle"
spin_start "Fetching ${TARBALL_URL}…"
if ! curl -fsSL "$TARBALL_URL" -o "$TMPDIR/repo.tar.gz" 2>/dev/null; then
    spin_stop "Download failed" "fail"
    abort "curl failed to fetch $TARBALL_URL"
fi
(cd "$TMPDIR" && tar -xzf repo.tar.gz)
EXTRACTED=$(find "$TMPDIR" -mindepth 1 -maxdepth 1 -type d -name "${REPO_NAME}-*" | head -1)
[[ -z "$EXTRACTED" ]] && { spin_stop "extract failed" "fail"; abort "extracted dir not found"; }
spin_stop "Bundle ready" "ok"

# ── 5. run notebooks 01, 02, 04, 05 ──────────────────────────────────────────
step "Run setup notebooks"

mkdir -p "$TMPDIR/state"
state_set() { echo "$2" > "$TMPDIR/state/$1"; }
state_get() { cat "$TMPDIR/state/$1" 2>/dev/null || echo ""; }

databricks workspace mkdirs "$PARENT_PATH" --profile "$PROFILE" >/dev/null 2>&1 || true

run_notebook() {
    # run_notebook  <local_path>  <ws_path>  <params_json>  <label>
    local local_path=$1 ws_path=$2 params_json=$3 label=$4
    # Strip "NN_" numeric prefix and ".py" suffix for cleaner display
    local nb_name
    nb_name=$(basename "$local_path" .py)
    nb_name=${nb_name#[0-9][0-9]_}
    printf "\n  %s%s %s%s\n" "$FG_YELLOW$BOLD" "$ARR" "$nb_name" "$RESET"

    spin_start "Uploading to $ws_path"
    databricks workspace import "$ws_path" \
        --file "$local_path" \
        --language PYTHON --format SOURCE --overwrite \
        --profile "$PROFILE" >/dev/null
    spin_stop "Uploaded" "ok"

    local submit_json
    submit_json=$(WS_PATH="$ws_path" PARAMS_JSON="$params_json" RUN_NAME="capstone-installer-$(basename "$ws_path")" \
        python3 -c '
import json, os
print(json.dumps({
    "run_name": os.environ["RUN_NAME"],
    "tasks": [{
        "task_key": "run",
        "notebook_task": {
            "notebook_path": os.environ["WS_PATH"],
            "base_parameters": json.loads(os.environ["PARAMS_JSON"]),
        },
    }],
}))')

    spin_start "Submitting one-shot job…"
    local submit_out run_id
    if ! submit_out=$(databricks jobs submit --profile "$PROFILE" --no-wait \
        --json "$submit_json" -o json 2>&1); then
        spin_stop "Submit failed" "fail"
        printf "      %s\n" "$submit_out"
        exit 1
    fi
    run_id=$(echo "$submit_out" | python3 -c "import json,sys;print(json.load(sys.stdin)['run_id'])")
    spin_stop "Submitted (run_id=$run_id)" "ok"
    info "Run URL: ${HOST}/jobs/runs/${run_id}"

    spin_start "$label"
    local last_state="" run_json life result
    while true; do
        run_json=$(databricks jobs get-run "$run_id" --profile "$PROFILE" -o json)
        life=$(echo "$run_json" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('state',{}).get('life_cycle_state',''))")
        if [[ "$life" != "$last_state" ]]; then
            spin_msg "$label  ·  $life"
            last_state=$life
        fi
        case "$life" in
            TERMINATED|SKIPPED|INTERNAL_ERROR) break ;;
        esac
        sleep 5
    done

    result=$(echo "$run_json" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('state',{}).get('result_state',''))")
    if [[ "$result" != "SUCCESS" ]]; then
        spin_stop "Run failed: $result" "fail"
        local msg
        msg=$(echo "$run_json" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('state',{}).get('state_message',''))")
        [[ -n "$msg" ]] && printf "      message: %s\n" "$msg"
        printf "      see: %s/jobs/runs/%s\n" "$HOST" "$run_id"
        exit 1
    fi
    spin_stop "Notebook succeeded" "ok"

    local task_run_id output_json nb_result
    task_run_id=$(echo "$run_json" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['tasks'][0]['run_id'])")
    output_json=$(databricks jobs get-run-output "$task_run_id" --profile "$PROFILE" -o json)
    nb_result=$(echo "$output_json" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('notebook_output',{}).get('result',''))")
    [[ -z "$nb_result" ]] && abort "Notebook produced no exit value."

    NB_RESULT="$nb_result" STATE_DIR="$TMPDIR/state" python3 -c '
import json, os
data = json.loads(os.environ["NB_RESULT"])
for k, v in data.items():
    with open(os.path.join(os.environ["STATE_DIR"], k), "w") as f:
        f.write(str(v))
print(",".join(data.keys()))
' > "$TMPDIR/.last_keys"
    info "Captured: $(tr ',' ' ' < "$TMPDIR/.last_keys")"
}

run_notebook \
    "$EXTRACTED/capstone/notebooks/01_generate_gold_data.py" \
    "$PARENT_PATH/01_generate_gold_data" \
    "$(python3 -c "import json;print(json.dumps({'catalog':'$CATALOG','schema':'$SCHEMA'}))")" \
    "Generating gold-layer Delta tables"

run_notebook \
    "$EXTRACTED/capstone/notebooks/02_create_lakebase_instance.py" \
    "$PARENT_PATH/02_create_lakebase_instance" \
    "$(python3 -c "import json;print(json.dumps({'instance_name':'$INSTANCE_NAME','uc_catalog_name':'$UC_LB_CATALOG','capacity':'$CAPACITY','database_name':'$DB_NAME'}))")" \
    "Provisioning Lakebase (1-3 min)"

run_notebook \
    "$EXTRACTED/capstone/notebooks/04_create_aibi_dashboard.py" \
    "$PARENT_PATH/04_create_aibi_dashboard" \
    "$(python3 -c "import json;print(json.dumps({'catalog':'$CATALOG','schema':'$SCHEMA','warehouse_id':'$WAREHOUSE_ID','dashboard_name':'$DASHBOARD_NAME','parent_path':'$PARENT_PATH'}))")" \
    "Creating AI/BI dashboard"

run_notebook \
    "$EXTRACTED/capstone/notebooks/05_create_genie_space.py" \
    "$PARENT_PATH/05_create_genie_space" \
    "$(python3 -c "import json;print(json.dumps({'catalog':'$CATALOG','schema':'$SCHEMA','warehouse_id':'$WAREHOUSE_ID','space_title':'$SPACE_TITLE','parent_path':'$PARENT_PATH'}))")" \
    "Creating Genie space"

# ── 6. drop scaffold + write .env ────────────────────────────────────────────
step "Drop the scaffold into your local working directory"
while true; do
    prompt_text DEST "Where should the scaffold be created?" "./capstone-app"
    DEST=$(python3 -c "import os,sys;print(os.path.abspath(os.path.expanduser('$DEST')))")
    if [[ -d "$DEST" && -n "$(ls -A "$DEST" 2>/dev/null)" ]]; then
        if prompt_confirm "  '$DEST' is not empty. Overwrite contents anyway?" "n"; then
            rm -rf "$DEST"
            break
        fi
        continue
    fi
    break
done

mkdir -p "$DEST"
cp -R "$EXTRACTED/capstone-scaffold/." "$DEST/"
cp -R "$EXTRACTED/capstone" "$DEST/capstone"
ok "Scaffold dropped at $DEST"

ENV_FILE="$DEST/app/.env"
mkdir -p "$DEST/app"
{
    echo "# Generated by capstone installer on $(date '+%Y-%m-%d %H:%M:%S')"
    echo "DATABRICKS_HOST=$HOST"
    echo "DATABRICKS_PROFILE=$PROFILE"
    echo "CAPSTONE_CATALOG=$(state_get CAPSTONE_CATALOG || echo "$CATALOG")"
    echo "CAPSTONE_SCHEMA=$(state_get CAPSTONE_SCHEMA || echo "$SCHEMA")"
    echo "WAREHOUSE_ID=$WAREHOUSE_ID"
    echo "DASHBOARD_ID=$(state_get DASHBOARD_ID)"
    echo "GENIE_SPACE_ID=$(state_get GENIE_SPACE_ID)"
    echo "PGHOST=$(state_get PGHOST)"
    echo "PGDATABASE=$(state_get PGDATABASE)"
    echo "PG_INSTANCE_NAME=$(state_get PG_INSTANCE_NAME)"
    echo "PG_UC_CATALOG=$(state_get PG_UC_CATALOG)"
    echo "SECRET_SCOPE=$(state_get SECRET_SCOPE)"
    echo "PARENT_PATH=$PARENT_PATH"
} > "$ENV_FILE"
ok "Wrote $ENV_FILE"

# ── 7. final summary ─────────────────────────────────────────────────────────
banner "All set  ·  happy hacking!"
DASH_ID=$(state_get DASHBOARD_ID)
GENIE_ID=$(state_get GENIE_SPACE_ID)
PGHOST_VAL=$(state_get PGHOST)
[[ -n "$DASH_ID"  ]] && printf "  %sDashboard:%s   %s/dashboardsv3/%s/published\n" "$BOLD" "$RESET" "$HOST" "$DASH_ID"
[[ -n "$GENIE_ID" ]] && printf "  %sGenie:%s       %s/genie/rooms/%s\n" "$BOLD" "$RESET" "$HOST" "$GENIE_ID"
if [[ -n "$PGHOST_VAL" ]]; then
    printf "  %sLakebase:%s    %s/%s\n" "$BOLD" "$RESET" "$PGHOST_VAL" "$(state_get PGDATABASE)"
    printf "  %sInstance:%s    %s\n"    "$BOLD" "$RESET" "$(state_get PG_INSTANCE_NAME)"
    printf "  %sSecret scope:%s %s\n"   "$BOLD" "$RESET" "$(state_get SECRET_SCOPE)"
fi
echo
printf "  %sNext steps:%s\n" "$BOLD" "$RESET"
printf "    cd %s\n" "$DEST"
printf "    cat CAPSTONE_TASKS.md            %s# your task list%s\n" "$DIM" "$RESET"
