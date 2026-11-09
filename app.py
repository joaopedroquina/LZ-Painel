import os
import re
import sys
import time
import socket
import platform
import threading
import traceback
import subprocess
import json

# Em programas sem console (--noconsole) stdout/stderr não existem; evita erros ao imprimir.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import psutil
import webview

try:
    import winreg
except ImportError:  # permite importar este arquivo fora do Windows
    winreg = None

NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DEVNULL = subprocess.DEVNULL
GUID = re.compile(r"^[0-9a-fA-F-]{36}$")
RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
UNINST = [r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
          r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"]
TOOLS = {"taskmgr": "taskmgr", "resmon": "resmon", "cleanmgr": "cleanmgr",
         "devmgmt": "devmgmt.msc", "diskmgmt": "diskmgmt.msc", "services": "services.msc",
         "msinfo": "msinfo32", "cmd": "cmd", "appwiz": "appwiz.cpl"}
SETTINGS = {"gaming-gamemode", "display-advancedgraphics", "network", "powersleep",
            "privacy-webcam", "privacy-microphone", "privacy-location",
            "privacy-general", "privacy-feedback"}

# nome do serviço: (título, descrição, início padrão, seguro desativar?)
SERVICES = {
    "DiagTrack": ("Telemetria do Windows", "Envia dados de diagnóstico e uso à Microsoft.", "auto", True),
    "dmwappushservice": ("Mensagens push WAP", "Usado pela telemetria; raramente necessário.", "demand", True),
    "WerSvc": ("Relatório de erros do Windows", "Envia relatórios de falhas à Microsoft.", "demand", True),
    "MapsBroker": ("Mapas baixados", "Atualiza mapas offline do Windows.", "delayed-auto", True),
    "RetailDemo": ("Demonstração para lojas", "Modo de demonstração de varejo.", "demand", True),
    "Fax": ("Fax", "Envio e recebimento de fax.", "demand", True),
    "WMPNetworkSvc": ("Compartilhamento do Media Player", "Compartilha mídia pela rede.", "demand", True),
    "lfsvc": ("Serviço de localização", "Apps de mapa e clima deixam de saber onde você está.", "demand", False),
    "SysMain": ("SysMain (Superfetch)", "Pré-carrega apps na memória. Pode ser desativado em SSD; em HD costuma ajudar.", "auto", False),
    "WSearch": ("Pesquisa do Windows", "Indexa arquivos para busca rápida. Sem ele a busca fica mais lenta.", "delayed-auto", False),
    "Spooler": ("Spooler de impressão", "Necessário para imprimir. Desative só se não usa impressora.", "auto", False),
    "XblGameSave": ("Xbox: salvamento na nuvem", "Sincroniza saves de jogos do Xbox e Game Pass.", "demand", False),
    "XblAuthManager": ("Xbox: autenticação", "Login da Xbox. Necessário para Game Pass e o app Xbox.", "demand", False),
    "XboxNetApiSvc": ("Xbox: rede", "Recursos de rede da Xbox.", "demand", False),
    "TabletInputService": ("Teclado de toque e manuscrito", "Usado em telas de toque e canetas.", "demand", False),
}

_temp = {"v": None}


def base():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def app_folder():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def log_error():
    try:
        with open(os.path.join(app_folder(), "painel_erro.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc() + "\n")
    except Exception:
        pass


def run(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout,
                           stdin=DEVNULL, creationflags=NOWIN)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception:
        return 1, ""


def hive(name):
    return winreg.HKEY_LOCAL_MACHINE if name == "HKLM" else winreg.HKEY_CURRENT_USER


def rval(key, name):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def temp_loop():
    """Lê a temperatura do sensor térmico do Windows a cada 15 s (nem todo PC informa)."""
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
           "(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
           "-ErrorAction SilentlyContinue | Select-Object -First 1).CurrentTemperature"]
    while True:
        value = None
        code, out = run(cmd, 25)
        try:
            c = float(out.strip().splitlines()[-1]) / 10 - 273.15
            if 5 < c < 120:
                value = round(c)
        except (ValueError, IndexError):
            pass
        _temp["v"] = value
        time.sleep(15)


def temp_dirs():
    return [
        ("Arquivos temporários do usuário", os.environ.get("TEMP", "")),
        ("Temp do Windows", os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp")),
        ("Cache de internet", os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "INetCache")),
    ]


def dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def iter_apps():
    seen = set()
    for hv, path in ((winreg.HKEY_LOCAL_MACHINE, UNINST[0]), (winreg.HKEY_LOCAL_MACHINE, UNINST[1]),
                     (winreg.HKEY_CURRENT_USER, UNINST[0])):
        try:
            key = winreg.OpenKey(hv, path)
        except OSError:
            continue
        with key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    with winreg.OpenKey(key, winreg.EnumKey(key, i)) as s:
                        name = rval(s, "DisplayName")
                        if not name or name in seen or rval(s, "SystemComponent") == 1 or rval(s, "ParentKeyName"):
                            continue
                        seen.add(name)
                        cmd = rval(s, "QuietUninstallString") or rval(s, "UninstallString")
                        if rval(s, "NoRemove") == 1:
                            cmd = None
                        yield {"name": str(name), "ver": str(rval(s, "DisplayVersion") or ""),
                               "pub": str(rval(s, "Publisher") or ""), "cmd": cmd}
                except OSError:
                    pass


class Api:
    def __init__(self):
        self._window = None
        self._maximized = False
        self._window_lock = threading.Lock()
        self._fps_lock = threading.Lock()

    def _fps_backup_path(self):
        folder = os.environ.get("LOCALAPPDATA")
        if not folder:
            raise OSError("Pasta de dados local indisponível")
        return os.path.join(folder, "LZPainel", "fps-backup.json")

    def _fps_backups(self):
        try:
            with open(self._fps_backup_path(), encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Backup inválido")
            for key, snapshot in data.items():
                if not isinstance(snapshot, dict):
                    raise ValueError("Registro de backup inválido")
                if key == "energy":
                    plan = snapshot.get("plan")
                    if not isinstance(plan, str) or not GUID.fullmatch(plan):
                        raise ValueError("Plano do backup inválido")
                elif (key not in SERVICES or not SERVICES[key][3] or
                      snapshot.get("start") not in {"auto", "delayed-auto", "demand"} or
                      not isinstance(snapshot.get("running"), bool)):
                    raise ValueError("Serviço do backup inválido")
            return data
        except FileNotFoundError:
            return {}

    def _fps_save(self, data):
        path = self._fps_backup_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)

    def fps_status(self):
        try:
            backups = self._fps_backups()
            error = None
        except (OSError, ValueError):
            backups, error = {}, "Não foi possível ler o backup dos ajustes."
        items = []
        for s in self.services():
            if not s["safe"]:
                continue
            name = s["name"]
            items.append({"id": name, "title": "Desativar " + s["title"],
                          "desc": s["desc"], "group": "priv" if name in
                          {"DiagTrack", "dmwappushservice", "WerSvc"} else "serv",
                          "active": not s["on"], "saved": name in backups,
                          "restart": not s["on"] and s["running"]})
        plans = self.plans()
        current = next((p for p in plans if p["on"]), None)
        if current:
            items.append({"id": "energy", "title": "Plano de alto desempenho",
                          "desc": "Prioriza desempenho; pode aumentar consumo e temperatura.",
                          "group": "energia", "active": bool(re.search(
                              r"alto|high|ultimate|máximo", current["name"], re.I)) or
                              current["id"].lower() == "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
                          "saved": "energy" in backups, "restart": False})
        return {"items": items, "error": error}

    def fps_set(self, key, apply):
        """Only existing safe-service/energy actions, with original state saved first."""
        if key != "energy" and (key not in SERVICES or not SERVICES[key][3]):
            return {"ok": False, "message": "Ajuste inválido"}
        if not isinstance(apply, bool):
            return {"ok": False, "message": "Estado inválido"}
        with self._fps_lock:
            try:
                backups = self._fps_backups()
                if apply:
                    if key not in backups:
                        if key == "energy":
                            current = next((p for p in self.plans() if p["on"]), None)
                            if not current:
                                raise ValueError("Plano atual indisponível")
                            snapshot = {"plan": current["id"]}
                        else:
                            service = psutil.win_service_get(key)
                            kind = service.start_type()
                            if kind == "disabled":
                                return {"ok": True, "message": "Ajuste já ativo antes do painel"}
                            start = {"automatic": "auto", "manual": "demand"}.get(kind)
                            if not start:
                                raise ValueError("Tipo de inicialização não suportado")
                            if start == "auto" and winreg:
                                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                        "SYSTEM\\CurrentControlSet\\Services\\" + key) as registry:
                                    if rval(registry, "DelayedAutoStart") == 1:
                                        start = "delayed-auto"
                            snapshot = {"start": start, "running": service.status() == "running"}
                        backups[key] = snapshot
                        self._fps_save(backups)  # Never change Windows if saving fails.
                    ok = self.setplan("high") if key == "energy" else self.set_service(key, False)
                else:
                    snapshot = backups.get(key)
                    if not snapshot:
                        return {"ok": False, "message": "Sem backup anterior para restaurar"}
                    if key == "energy":
                        plan = snapshot.get("plan", "")
                        if not GUID.fullmatch(plan):
                            raise ValueError("Plano do backup inválido")
                        ok = self.setplan(plan)
                    else:
                        start = snapshot.get("start")
                        if start not in {"auto", "delayed-auto", "demand"}:
                            raise ValueError("Backup do serviço inválido")
                        ok = run(["sc", "config", key, "start=", start])[0] == 0
                        if ok:
                            running = psutil.win_service_get(key).status() == "running"
                            wanted = snapshot.get("running") is True
                            if running != wanted:
                                ok = run(["sc", "start" if wanted else "stop", key])[0] == 0
                    if ok:
                        del backups[key]
                        self._fps_save(backups)
                return {"ok": bool(ok), "message": ("Ajuste aplicado" if apply else
                        "Estado anterior restaurado") if ok else
                        "Não foi possível concluir. Verifique as permissões de administrador."}
            except (OSError, ValueError, KeyError, TypeError) as e:
                return {"ok": False, "message": "Ajuste não concluído: " + str(e)}

    def window_state(self):
        return {"maximized": self._maximized}

    def window_action(self, action):
        if self._window is None or action not in {"minimize", "maximize", "close"}:
            return False
        with self._window_lock:
            if action == "minimize":
                self._window.minimize()
            elif action == "maximize":
                if self._maximized:
                    self._window.restore()
                else:
                    self._window.maximize()
            else:
                self._window.destroy()
        return True

    def _set_maximized(self, value):
        self._maximized = value
        try:
            self._window.evaluate_js(
                "window.setWindowMaximized && window.setWindowMaximized(%s)"
                % ("true" if value else "false")
            )
        except Exception:
            pass  # A página pode ainda estar carregando ou fechando.

    def stats(self):
        vm = psutil.virtual_memory()
        return {"cpu": psutil.cpu_percent(interval=None),
                "ram_used": vm.used / 2**30, "ram_total": vm.total / 2**30,
                "disk": psutil.disk_usage(os.path.abspath(os.sep)).percent,
                "disk_free": psutil.disk_usage(os.path.abspath(os.sep)).free,
                "disk_total": psutil.disk_usage(os.path.abspath(os.sep)).total,
                "temp": _temp["v"]}

    def info(self):
        cpu = platform.processor()
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                cpu = rval(k, "ProcessorNameString") or cpu
        except Exception:
            pass
        d = psutil.disk_usage(os.path.abspath(os.sep))
        return {"os": f"{platform.system()} {platform.release()}", "cpu": (cpu or "").strip(),
                "cores": f"{psutil.cpu_count(False)} núcleos / {psutil.cpu_count()} threads",
                "ram": psutil.virtual_memory().total / 2**30,
                "disk_total": d.total, "disk_free": d.free,
                "uptime": time.time() - psutil.boot_time()}

    def procs(self):
        out = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                out.append({"pid": p.info["pid"], "name": p.info["name"], "mem": p.info["memory_info"].rss})
            except Exception:
                pass
        return sorted(out, key=lambda x: -x["mem"])[:15]

    def kill(self, pid):
        try:
            if int(pid) == os.getpid():
                return False
            psutil.Process(int(pid)).terminate()
            return True
        except Exception:
            return False

    def ping(self):
        res = []
        for label, host in (("Cloudflare (1.1.1.1)", "1.1.1.1"), ("Google DNS (8.8.8.8)", "8.8.8.8"),
                            ("google.com", "google.com")):
            best = None
            for _ in range(2):
                t = time.perf_counter()
                try:
                    socket.create_connection((host, 443), 1.5).close()
                    ms = round((time.perf_counter() - t) * 1000)
                    best = ms if best is None else min(best, ms)
                except OSError:
                    pass
            res.append([label, best])
        return res

    def flushdns(self):
        return run(["ipconfig", "/flushdns"])[0] == 0

    def startup(self):
        out = []
        for hn in ("HKCU", "HKLM"):
            try:
                with winreg.OpenKey(hive(hn), RUN) as k:
                    i = 0
                    while True:
                        try:
                            n, v, _ = winreg.EnumValue(k, i)
                        except OSError:
                            break
                        i += 1
                        on = True
                        try:
                            with winreg.OpenKey(hive(hn), APPROVED) as a:
                                raw = rval(a, n)
                                on = not (raw and raw[0] % 2 == 1)
                        except OSError:
                            pass
                        out.append({"name": n, "cmd": str(v), "hive": hn, "on": on})
            except OSError:
                pass
        return out

    def set_startup(self, name, hn, on):
        try:
            with winreg.CreateKeyEx(hive(hn), APPROVED, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, name, 0, winreg.REG_BINARY, bytes([2 if on else 3]) + bytes(11))
            return True
        except OSError:
            return False

    def plans(self):
        _, out = run(["powercfg", "/list"])
        return [{"id": g, "name": n, "on": bool(a)}
                for g, n, a in re.findall(r"([0-9a-fA-F-]{36})\s+\((.+?)\)\s*(\*)?", out)]

    def setplan(self, plan):
        alias = {"high": "SCHEME_MIN", "balanced": "SCHEME_BALANCED"}
        if plan not in alias and not GUID.match(str(plan)):
            return False
        return run(["powercfg", "/setactive", alias.get(plan, plan)])[0] == 0

    def scan(self):
        return [[l, dir_size(p)] for l, p in temp_dirs() if p and os.path.isdir(p)]

    def clean(self):
        freed = 0
        for _, p in temp_dirs():
            if not p or not os.path.isdir(p):
                continue
            for root, dirs, files in os.walk(p, topdown=False):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        size = os.path.getsize(fp)
                        os.remove(fp)
                        freed += size
                    except OSError:
                        pass
                for d in dirs:
                    try:
                        os.rmdir(os.path.join(root, d))
                    except OSError:
                        pass
        return freed

    def apps(self):
        lst = sorted(iter_apps(), key=lambda x: x["name"].lower())
        return [{"name": x["name"], "ver": x["ver"], "pub": x["pub"], "can": bool(x["cmd"])} for x in lst]

    def uninstall(self, name):
        # o comando vem sempre do registro do Windows, nunca da página
        app = next((x for x in iter_apps() if x["name"] == name), None)
        if not app or not app["cmd"]:
            return "erro"
        cmd = app["cmd"]
        if cmd.lower().lstrip('"').startswith("msiexec"):
            cmd = re.sub(r"/I(?=\s*\{)", "/X", cmd, flags=re.I)
        try:
            subprocess.Popen(cmd, shell=True, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL,
                             creationflags=NOWIN).wait(timeout=600)
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            return "erro"
        return "aberto" if any(x["name"] == name for x in iter_apps()) else "removido"

    def services(self):
        out = []
        for name, (title, desc, _, safe) in SERVICES.items():
            try:
                s = psutil.win_service_get(name)
                out.append({"name": name, "title": title, "desc": desc, "safe": safe,
                            "on": s.start_type() != "disabled", "running": s.status() == "running"})
            except Exception:
                pass  # serviço não existe neste PC
        return out

    def set_service(self, name, on):
        if name not in SERVICES:
            return False
        start = SERVICES[name][2]
        if on:
            code, _ = run(["sc", "config", name, "start=", start])
            if code == 0 and start != "demand":
                run(["sc", "start", name])
        else:
            run(["sc", "stop", name])
            code, _ = run(["sc", "config", name, "start=", "disabled"])
        return code == 0

    def freemem(self):
        """Esvazia o working set dos processos (libera RAM sem fechar nada). Retorna bytes liberados."""
        if os.name != "nt":
            return 0
        import ctypes
        from ctypes import wintypes
        k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
        before = psutil.virtual_memory().available
        for pid in psutil.pids():
            try:
                h = k32.OpenProcess(0x0100 | 0x0400, False, pid)  # SET_QUOTA | QUERY_INFORMATION
                if h:
                    psapi.EmptyWorkingSet(h)
                    k32.CloseHandle(h)
            except Exception:
                pass
        time.sleep(0.6)
        return max(0, psutil.virtual_memory().available - before)

    def dns_status(self):
        code, out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                         "$a = Get-NetAdapter | Where-Object Status -eq 'Up'; "
                         "($a | Get-DnsClientServerAddress -AddressFamily IPv4).ServerAddresses -join ', '"], 30)
        out = out.strip()
        if code != 0 or not out:
            return None
        names = {"1.1.1.1": "Cloudflare", "8.8.8.8": "Google"}
        first = out.split(",")[0].strip()
        return f"{out} ({names[first]})" if first in names else out

    def set_dns(self, kind):
        servers = {"cloudflare": "'1.1.1.1','1.0.0.1'", "google": "'8.8.8.8','8.8.4.4'"}
        base_cmd = "Get-NetAdapter | Where-Object Status -eq 'Up' | "
        if kind == "auto":
            ps = base_cmd + "Set-DnsClientServerAddress -ResetServerAddresses"
        elif kind in servers:
            ps = base_cmd + f"Set-DnsClientServerAddress -ServerAddresses {servers[kind]}"
        else:
            return False
        code, _ = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], 60)
        if code == 0:
            run(["ipconfig", "/flushdns"])
        return code == 0

    def abrir(self, key):
        try:
            if key in TOOLS:
                os.startfile(TOOLS[key])
            elif key in SETTINGS:
                os.startfile("ms-settings:" + key)
            else:
                return False
            return True
        except Exception:
            return False

    def restore(self):
        code, _ = run(["powershell", "-NoProfile", "-Command",
                       "Checkpoint-Computer -Description 'Painel' -RestorePointType MODIFY_SETTINGS"], 180)
        if code == 0:
            return "Ponto de restauração criado"
        return "Não foi possível criar. Ative a Proteção do Sistema e execute como administrador."


def main():
    psutil.cpu_percent(interval=None)
    if os.name == "nt":
        threading.Thread(target=temp_loop, daemon=True).start()
    api = Api()
    window = webview.create_window("LZ Painel", os.path.join(base(), "index.html"),
                          js_api=api, width=1440, height=900, min_size=(1000, 700),
                          frameless=True, easy_drag=False, resizable=True,
                          background_color="#171a20")
    api._window = window
    window.events.maximized += lambda: api._set_maximized(True)
    window.events.restored += lambda: api._set_maximized(False)
    webview.start()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_error()
        raise
