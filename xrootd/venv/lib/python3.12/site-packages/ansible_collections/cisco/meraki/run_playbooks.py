#!/usr/bin/env python3
"""
Ejecuta todos los playbooks de Ansible y genera un reporte de exitosos y fallidos.

Uso:
    python3 run_playbooks.py
    python3 run_playbooks.py --credentials playbooks/credentials.yml
    python3 run_playbooks.py --dir playbooks --timeout 120
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path("playbooks_logs")
SKIP_FILES = {"credentials.template", "credentials.yml", "hosts"}
SKIP_EXTENSIONS = {".template"}

# Archivos de vars que deben existir para que el playbook corra
# Si no existen se saltea con razon clara
REQUIRED_VAR_FILES_PATTERN = re.compile(
    r"file:\s+['\"]?([^\s'\"#]+\.ya?ml)['\"]?|"
    r"vars_files:\s*\n(?:\s+-\s+['\"]?([^\s'\"#]+\.ya?ml)['\"]?\n)+",
    re.MULTILINE,
)


def find_playbooks(directory: Path) -> list[Path]:
    playbooks = []
    for path in sorted(directory.iterdir()):
        if path.is_dir():
            continue
        if path.name in SKIP_FILES:
            continue
        if path.suffix in SKIP_EXTENSIONS:
            continue
        if path.suffix not in (".yml", ".yaml"):
            continue
        # Solo archivos que tengan 'hosts:' (son playbooks, no vars files)
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            if "hosts:" not in content:
                continue
        except Exception:
            continue
        playbooks.append(path)
    return playbooks


def missing_var_files(playbook: Path) -> list[str]:
    """Devuelve lista de var files referenciados pero no encontrados en disco."""
    try:
        content = playbook.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    missing = []
    for match in REQUIRED_VAR_FILES_PATTERN.finditer(content):
        fname = match.group(1) or match.group(2)
        if not fname:
            continue
        # Buscar relativo al directorio del playbook
        candidate = playbook.parent / fname
        if not candidate.exists():
            missing.append(fname)
    return missing


def run_playbook(
    playbook: Path,
    extra_vars_file: str | None,
    timeout: int,
) -> tuple[str, int, str]:
    """
    Corre un playbook. Devuelve (status, exit_code, output).
    status: 'PASS' | 'FAIL' | 'TIMEOUT' | 'SKIP'
    """
    cmd = ["ansible-playbook", "-i", "localhost,", str(playbook)]
    if extra_vars_file:
        cmd += ["-e", f"@{extra_vars_file}"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=playbook.parent.parent,  # raiz del repo
        )
        output = result.stdout + result.stderr
        status = "PASS" if result.returncode == 0 else "FAIL"
        return status, result.returncode, output

    except subprocess.TimeoutExpired:
        return "TIMEOUT", -1, f"Timeout ({timeout}s)"

    except FileNotFoundError:
        return "FAIL", -1, "ansible-playbook no encontrado. Instala Ansible."

    except Exception as e:
        return "FAIL", -1, str(e)


def extract_error(output: str) -> str:
    """Extrae la primera linea de error relevante del output."""
    for line in output.splitlines():
        if any(k in line for k in ("fatal:", "ERROR!", "error:", "Exception")):
            return line.strip()[:200]
    return output.strip().splitlines()[-1][:200] if output.strip() else "sin detalle"


def save_log(playbook_name: str, output: str, exit_code: int) -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"{playbook_name}_{ts}.log"
    log_path.write_text(
        f"Playbook : {playbook_name}\n"
        f"Fecha    : {datetime.now()}\n"
        f"Exit code: {exit_code}\n"
        f"{'='*60}\n"
        f"{output}\n",
        encoding="utf-8",
    )
    return log_path


def main():
    parser = argparse.ArgumentParser(description="Corre todos los playbooks y genera reporte")
    parser.add_argument("--dir", default="playbooks", help="Directorio de playbooks")
    parser.add_argument("--credentials", default=None, help="Archivo de credenciales (extra vars)")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout por playbook en segundos")
    parser.add_argument("--report", default="playbooks_report.txt", help="Archivo de reporte")
    args = parser.parse_args()

    pb_dir = Path(args.dir)
    if not pb_dir.exists():
        print(f"ERROR: directorio '{pb_dir}' no existe.")
        sys.exit(1)

    creds = args.credentials
    if creds and not Path(creds).exists():
        print(f"ADVERTENCIA: credenciales '{creds}' no encontradas, se omiten.")
        creds = None

    playbooks = find_playbooks(pb_dir)
    total = len(playbooks)
    if total == 0:
        print("No se encontraron playbooks.")
        sys.exit(0)

    print(f"\n{'='*60}")
    print(f"  Meraki Playbook Runner")
    print(f"  Playbooks : {total}")
    print(f"  Credenciales: {creds or '(ninguna)'}")
    print(f"  Timeout   : {args.timeout}s")
    print(f"  Reporte   : {args.report}")
    print(f"{'='*60}\n")

    passed, failed, skipped = [], [], []

    for i, pb in enumerate(playbooks, 1):
        name = pb.name
        prefix = f"[{i:>3}/{total}]"

        # Verificar dependencias antes de correr
        missing = missing_var_files(pb)
        if missing:
            reason = f"Vars file(s) no encontrado(s): {', '.join(missing)}"
            print(f"{prefix} SKIP  {name}")
            print(f"          {reason}")
            skipped.append({"name": name, "reason": reason})
            continue

        print(f"{prefix} RUN   {name} ...", end=" ", flush=True)
        status, exit_code, output = run_playbook(pb, creds, args.timeout)

        if status == "PASS":
            print("PASS")
            passed.append({"name": name})
        else:
            error = extract_error(output)
            log_path = save_log(name, output, exit_code)
            print(f"{status}")
            print(f"          {error}")
            print(f"          Log: {log_path}")
            failed.append({"name": name, "status": status, "error": error, "log": str(log_path)})

    # Generar reporte
    lines = [
        "=" * 60,
        "  REPORTE DE EJECUCION DE PLAYBOOKS",
        f"  Fecha   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        f"  Total   : {total}",
        f"  Exitosos: {len(passed)}",
        f"  Fallidos: {len(failed)}",
        f"  Saltados: {len(skipped)} (dependencias faltantes)",
        "=" * 60,
        "",
    ]

    if passed:
        lines += ["EXITOSOS", "-" * 60]
        for r in passed:
            lines.append(f"  OK   {r['name']}")
        lines.append("")

    if failed:
        lines += ["FALLIDOS", "-" * 60]
        for r in failed:
            lines.append(f"  FAIL [{r['status']}] {r['name']}")
            lines.append(f"       Error: {r['error']}")
            lines.append(f"       Log  : {r['log']}")
        lines.append("")

    if skipped:
        lines += ["SALTADOS (dependencia faltante)", "-" * 60]
        for r in skipped:
            lines.append(f"  SKIP {r['name']}")
            lines.append(f"       {r['reason']}")
        lines.append("")

    report = "\n".join(lines)
    print("\n" + report)
    Path(args.report).write_text(report, encoding="utf-8")
    print(f"Reporte guardado en: {args.report}")

    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
