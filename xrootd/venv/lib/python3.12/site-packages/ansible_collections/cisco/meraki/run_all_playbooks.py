#!/usr/bin/env python3
"""
Script para ejecutar todos los playbooks de Ansible y generar un informe
con los resultados de éxito y fallos.
"""

import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


class PlaybookRunner:
    def __init__(self, playbooks_dir: str = "playbooks", logs_dir: str = "playbooks_logs"):
        self.playbooks_dir = Path(playbooks_dir)
        self.logs_dir = Path(logs_dir)
        self.results: List[Dict] = []
        
        # Crear directorio de logs si no existe
        self.logs_dir.mkdir(exist_ok=True)
        
        # Códigos de salida de ansible-playbook y sus significados
        self.exit_codes = {
            0: "Éxito - El playbook se ejecutó correctamente",
            1: "Error general - Ocurrió un error durante la ejecución",
            2: "Tareas fallidas - Una o más tareas fallaron en uno o más hosts",
            3: "Hosts inalcanzables - Uno o más hosts no fueron alcanzables",
            4: "Error de sintaxis - Problemas con la sintaxis del playbook o opciones",
            5: "Mal uso - Uso incorrecto de ansible-playbook",
            99: "Error de usuario - Error causado por el usuario",
            250: "Error inesperado - Error inesperado en ansible-playbook"
        }
        
    def find_playbooks(self) -> List[Path]:
        """Encuentra todos los archivos playbook (.yml y .yaml) en el directorio."""
        playbooks = []
        if not self.playbooks_dir.exists():
            print(f"Error: El directorio {self.playbooks_dir} no existe")
            sys.exit(1)
            
        for ext in ['*.yml', '*.yaml']:
            playbooks.extend(self.playbooks_dir.glob(ext))
        
        # Excluir archivos que no son playbooks (como credentials.template)
        playbooks = [p for p in playbooks if p.is_file() and 
                    not p.name.endswith('.template')]
        
        return sorted(playbooks)
    
    def get_exit_code_meaning(self, exit_code: int) -> str:
        """
        Obtiene el significado de un código de salida de ansible-playbook.
        
        Args:
            exit_code: Código de salida
            
        Returns:
            Descripción del código de salida
        """
        return self.exit_codes.get(exit_code, f"Código desconocido: {exit_code}")
    
    def check_missing_deps(self, playbook_path: Path) -> List[str]:
        """Detecta vars files referenciados en el playbook que no existen en disco."""
        missing = []
        try:
            with open(playbook_path, encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return missing

        # Buscar include_vars con file: o vars_files
        patterns = [
            r"file:\s+['\"]?([^\s'\"]+\.ya?ml)['\"]?",
            r"vars_files:\s*\n\s+-\s+['\"]?([^\s'\"]+\.ya?ml)['\"]?",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                dep_file = match.group(1)
                # Resolver relativo al directorio del playbook
                dep_path = playbook_path.parent / dep_file
                if not dep_path.exists():
                    missing.append(dep_file)
        return missing

    def run_playbook(self, playbook_path: Path) -> Tuple[bool, str, str, int]:
        """
        Ejecuta un playbook y retorna (éxito, stdout, stderr, exit_code).

        Args:
            playbook_path: Ruta al playbook

        Returns:
            Tupla con (éxito, stdout, stderr, exit_code)
        """
        print(f"\n{'='*80}")
        print(f"Ejecutando: {playbook_path.name}")
        print(f"{'='*80}")

        # Pre-check: detectar dependencias faltantes antes de correr
        missing_deps = self.check_missing_deps(playbook_path)
        if missing_deps:
            msg = f"Dependencias faltantes: {', '.join(missing_deps)}"
            print(f"⚠ {playbook_path.name} - SKIP ({msg})")
            return None, "", msg, -2
        
        try:
            # Ejecutar ansible-playbook con captura de salida
            result = subprocess.run(
                ['ansible-playbook', '-i', 'localhost,', str(playbook_path)],
                capture_output=True,
                text=True,
                timeout=600,  # Timeout de 10 minutos por playbook
                cwd=self.playbooks_dir.parent
            )
            
            success = result.returncode == 0
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode

            if success:
                print(f"✓ {playbook_path.name} - ÉXITO")
            else:
                exit_meaning = self.get_exit_code_meaning(exit_code)
                print(f"✗ {playbook_path.name} - FALLÓ")
                print(f"  Código de salida: {exit_code} - {exit_meaning}")
                print(f"  Log completo se guardará en: {self.logs_dir}/")

            return success, stdout, stderr, exit_code
            
        except subprocess.TimeoutExpired:
            error_msg = f"Timeout: El playbook tardó más de 10 minutos en ejecutarse"
            print(f"✗ {playbook_path.name} - TIMEOUT")
            return False, "", error_msg, -1
            
        except FileNotFoundError:
            error_msg = "Error: ansible-playbook no se encontró. ¿Está instalado Ansible?"
            print(f"✗ {playbook_path.name} - ERROR: {error_msg}")
            return False, "", error_msg, -1
            
        except Exception as e:
            error_msg = f"Error inesperado: {str(e)}"
            print(f"✗ {playbook_path.name} - ERROR: {error_msg}")
            return False, "", error_msg, -1
    
    def save_logs(self, playbook_name: str, stdout: str, stderr: str, exit_code: int) -> str:
        """
        Guarda los logs completos de un playbook fallido en un archivo.
        
        Args:
            playbook_name: Nombre del playbook
            stdout: Salida estándar
            stderr: Salida de error
            exit_code: Código de salida
            
        Returns:
            Ruta al archivo de log guardado
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f"{playbook_name}_{timestamp}.log"
        log_path = self.logs_dir / log_filename
        
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"LOG DE EJECUCIÓN: {playbook_name}\n")
            f.write("=" * 80 + "\n")
            f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Código de salida: {exit_code} - {self.get_exit_code_meaning(exit_code)}\n")
            f.write("\n" + "=" * 80 + "\n")
            f.write("SALIDA ESTÁNDAR (STDOUT)\n")
            f.write("=" * 80 + "\n")
            f.write(stdout)
            f.write("\n\n" + "=" * 80 + "\n")
            f.write("SALIDA DE ERROR (STDERR)\n")
            f.write("=" * 80 + "\n")
            f.write(stderr)
            f.write("\n" + "=" * 80 + "\n")
        
        return str(log_path)
    
    def extract_error_reason(self, stdout: str, stderr: str) -> str:
        """
        Extrae la razón del fallo de la salida de ansible-playbook.
        
        Args:
            stdout: Salida estándar
            stderr: Salida de error
            
        Returns:
            Razón del fallo extraída
        """
        # Combinar stdout y stderr para buscar errores
        output = stdout + "\n" + stderr
        
        # Detectar errores específicos conocidos
        if "requires Python 3.10" in output or "Python 3.10 at minimum" in output:
            python_version = sys.version.split()[0]
            return f"❌ ERROR DE VERSIÓN DE PYTHON: Se requiere Python 3.10+, pero estás usando {python_version}. Actualiza Python o usa un entorno virtual con Python 3.10+."
        
        if "Could not find or access" in output:
            match = re.search(r"Could not find or access '([^']+)'", output)
            if match:
                return f"❌ ARCHIVO NO ENCONTRADO: No se pudo encontrar el archivo '{match.group(1)}'"
        
        if "authentication failed" in output.lower() or "unauthorized" in output.lower():
            return "❌ ERROR DE AUTENTICACIÓN: Credenciales inválidas o expiradas. Verifica tu API key de Meraki."
        
        if "network_id" in output.lower() and ("required" in output.lower() or "missing" in output.lower()):
            return "❌ VARIABLE FALTANTE: Se requiere 'network_id' pero no está definida en el playbook."
        
        if "org_id" in output.lower() and ("required" in output.lower() or "missing" in output.lower()):
            return "❌ VARIABLE FALTANTE: Se requiere 'org_id' pero no está definida en el playbook."
        
        # Buscar patrones comunes de error
        error_patterns = [
            r'ERROR! (.+?)(?:\n|$)',
            r'fatal: (.+?)(?:\n|$)',
            r'failed: (.+?)(?:\n|$)',
            r'Error: (.+?)(?:\n|$)',
            r'Exception: (.+?)(?:\n|$)',
        ]
        
        reasons = []
        for pattern in error_patterns:
            matches = re.findall(pattern, output, re.IGNORECASE | re.MULTILINE)
            if matches:
                reasons.extend(matches[:2])  # Tomar máximo 2 coincidencias por patrón
        
        if reasons:
            # Unir las razones y limitar la longitud
            reason = "; ".join(reasons[:3])
            if len(reason) > 200:
                reason = reason[:200] + "..."
            return reason
        
        # Si no se encontró un patrón específico, buscar las últimas líneas de error
        lines = output.split('\n')
        error_lines = [line for line in lines if any(keyword in line.lower() 
                    for keyword in ['error', 'fatal', 'failed', 'exception'])]
        
        if error_lines:
            # Tomar las últimas líneas de error
            last_errors = error_lines[-3:]
            reason = " | ".join(last_errors)
            if len(reason) > 200:
                reason = reason[:200] + "..."
            return reason
        
        # Si no se encontró nada específico, retornar un mensaje genérico
        if stderr:
            return stderr[:200] if len(stderr) <= 200 else stderr[:200] + "..."
        
        return "Razón desconocida (revisar logs)"
    
    def categorize_error(self, error_reason: str) -> str:
        """
        Categoriza un error en un tipo específico.
        
        Args:
            error_reason: Razón del error
            
        Returns:
            Categoría del error
        """
        if "VERSIÓN DE PYTHON" in error_reason:
            return "Versión de Python incompatible"
        elif "ARCHIVO NO ENCONTRADO" in error_reason:
            return "Archivo faltante"
        elif "AUTENTICACIÓN" in error_reason:
            return "Error de autenticación"
        elif "VARIABLE FALTANTE" in error_reason:
            return "Variable faltante"
        else:
            return "Otro error"
    
    def check_python_version(self) -> None:
        """Verifica la versión de Python y muestra advertencias si es necesario."""
        python_version = sys.version_info
        current_version = f"{python_version.major}.{python_version.minor}.{python_version.micro}"
        
        print(f"Python detectado: {current_version}")
        
        if python_version < (3, 10):
            print(f"\n⚠️  ADVERTENCIA: Estás usando Python {current_version}")
            print("   La librería Meraki SDK requiere Python 3.10 o superior.")
            print("   Muchos playbooks pueden fallar por esta razón.")
            print("   Considera actualizar Python o usar un entorno virtual con Python 3.10+")
            print("")
        
    def run_all(self) -> None:
        """Ejecuta todos los playbooks y almacena los resultados."""
        playbooks = self.find_playbooks()
        
        if not playbooks:
            print(f"No se encontraron playbooks en {self.playbooks_dir}")
            return
        
        print(f"\n{'='*80}")
        print(f"Encontrados {len(playbooks)} playbooks para ejecutar")
        print(f"Logs de playbooks fallidos se guardarán en: {self.logs_dir}/")
        print(f"{'='*80}\n")
        
        # Verificar versión de Python
        self.check_python_version()
        
        for i, playbook in enumerate(playbooks, 1):
            print(f"\n[{i}/{len(playbooks)}] Procesando: {playbook.name}")
            
            success, stdout, stderr, exit_code = self.run_playbook(playbook)

            # None = skipped por dependencias faltantes
            if success is None:
                self.results.append({
                    'playbook': playbook.name,
                    'path': str(playbook),
                    'success': None,
                    'exit_code': -2,
                    'exit_meaning': 'Skipped',
                    'error_reason': stderr,
                    'error_category': 'Dependencia faltante',
                    'stdout': '',
                    'stderr': stderr,
                    'log_file': None,
                })
                continue

            error_reason = ""
            exit_meaning = ""
            error_category = ""
            if not success:
                error_reason = self.extract_error_reason(stdout, stderr)
                exit_meaning = self.get_exit_code_meaning(exit_code)
                error_category = self.categorize_error(error_reason)

            log_file = None
            if not success:
                log_file = self.save_logs(playbook.name, stdout, stderr, exit_code)

            self.results.append({
                'playbook': playbook.name,
                'path': str(playbook),
                'success': success,
                'exit_code': exit_code,
                'exit_meaning': exit_meaning,
                'error_reason': error_reason,
                'error_category': error_category,
                'stdout': stdout,
                'stderr': stderr,
                'log_file': log_file,
            })
    
    def generate_report(self, output_file: str = None) -> str:
        """
        Genera un informe con los resultados de la ejecución.
        
        Args:
            output_file: Archivo donde guardar el informe (opcional)
            
        Returns:
            Contenido del informe
        """
        total = len(self.results)
        successful = sum(1 for r in self.results if r['success'] is True)
        skipped = sum(1 for r in self.results if r['success'] is None)
        failed = total - successful - skipped
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("INFORME DE EJECUCIÓN DE PLAYBOOKS")
        report_lines.append("=" * 80)
        report_lines.append(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"Total de playbooks: {total}")
        report_lines.append(f"Éxitos : {successful} ({successful/total*100:.1f}%)" if total > 0 else "Éxitos: 0")
        report_lines.append(f"Fallos : {failed} ({failed/total*100:.1f}%)" if total > 0 else "Fallos: 0")
        report_lines.append(f"Saltados: {skipped} (dependencias faltantes)" if skipped > 0 else "Saltados: 0")
        if failed > 0:
            report_lines.append(f"Logs de playbooks fallidos guardados en: {self.logs_dir}/")
        report_lines.append("")

        if successful > 0:
            report_lines.append("-" * 80)
            report_lines.append("PLAYBOOKS EXITOSOS")
            report_lines.append("-" * 80)
            for result in self.results:
                if result['success'] is True:
                    report_lines.append(f"✓ {result['playbook']}")
            report_lines.append("")

        if skipped > 0:
            report_lines.append("-" * 80)
            report_lines.append("PLAYBOOKS SALTADOS (dependencia faltante)")
            report_lines.append("-" * 80)
            for result in self.results:
                if result['success'] is None:
                    report_lines.append(f"⚠ {result['playbook']}")
                    report_lines.append(f"  {result['error_reason']}")
            report_lines.append("")

        if failed > 0:
            # Agrupar errores por categoría
            errors_by_category = defaultdict(list)
            for result in self.results:
                if result['success'] is False:
                    category = result.get('error_category', 'Otro error')
                    errors_by_category[category].append(result)
            
            report_lines.append("-" * 80)
            report_lines.append("RESUMEN DE ERRORES POR CATEGORÍA")
            report_lines.append("-" * 80)
            for category, errors in sorted(errors_by_category.items(), key=lambda x: len(x[1]), reverse=True):
                report_lines.append(f"{category}: {len(errors)} playbook(s)")
            report_lines.append("")
            
            report_lines.append("-" * 80)
            report_lines.append("PLAYBOOKS FALLIDOS (DETALLES)")
            report_lines.append("-" * 80)
            
            # Mostrar primero los errores más comunes
            for category in sorted(errors_by_category.keys(), key=lambda x: len(errors_by_category[x]), reverse=True):
                if len(errors_by_category[category]) > 0:
                    report_lines.append("")
                    report_lines.append(f"📋 {category.upper()} ({len(errors_by_category[category])} playbook(s))")
                    report_lines.append("-" * 80)
                    
                    for result in errors_by_category[category]:
                        report_lines.append(f"✗ {result['playbook']}")
                        if result['exit_code'] != -1:
                            report_lines.append(f"  Código de salida: {result['exit_code']} - {result['exit_meaning']}")
                        if result['error_reason']:
                            report_lines.append(f"  Razón: {result['error_reason']}")
                        if result.get('log_file'):
                            report_lines.append(f"  Log completo: {result['log_file']}")
                        report_lines.append("")
        
        report_content = "\n".join(report_lines)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_content)
            print(f"\n✓ Informe guardado en: {output_file}")
        
        return report_content


def main():
    """Función principal."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Ejecuta todos los playbooks de Ansible y genera un informe'
    )
    parser.add_argument(
        '--playbooks-dir',
        default='playbooks',
        help='Directorio donde están los playbooks (default: playbooks)'
    )
    parser.add_argument(
        '--output',
        '-o',
        default='playbooks_report.txt',
        help='Archivo de salida para el informe (default: playbooks_report.txt)'
    )
    parser.add_argument(
        '--no-report-file',
        action='store_true',
        help='No guardar el informe en un archivo, solo mostrarlo en consola'
    )
    parser.add_argument(
        '--logs-dir',
        default='playbooks_logs',
        help='Directorio donde guardar los logs de playbooks fallidos (default: playbooks_logs)'
    )
    
    args = parser.parse_args()
    
    runner = PlaybookRunner(playbooks_dir=args.playbooks_dir, logs_dir=args.logs_dir)
    
    try:
        runner.run_all()
        
        if args.no_report_file:
            report = runner.generate_report()
            print("\n" + report)
        else:
            report = runner.generate_report(output_file=args.output)
            print("\n" + report)
        
        # Retornar código de salida apropiado
        failed_count = sum(1 for r in runner.results if r['success'] is False)
        sys.exit(0 if failed_count == 0 else 1)
        
    except KeyboardInterrupt:
        print("\n\nEjecución interrumpida por el usuario")
        sys.exit(130)
    except Exception as e:
        print(f"\nError fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

