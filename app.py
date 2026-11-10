import os
import webbrowser
import re
import json
import glob
import hashlib
import shutil
import tempfile
import sys
import time
import socket
import platform
import threading
import traceback
import subprocess

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
            "privacy-general", "privacy-feedback", "windowsupdate",
            "windowsupdate-optionalupdates", "display-advanced", "gaming-gamedvr"}

# nome do serviço: (título, descrição, início padrão, seguro desativar?)
SERVICES = {
    "DiagTrack": ("Telemetria do Windows", "Envia dados de diagnóstico e uso à Microsoft.", "auto", True),
    "RemoteRegistry": ("Registro Remoto", "Permite modificar remotamente o registro; normalmente não é necessário em PCs domésticos.", "demand", False),
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
        self._interface_lock = threading.RLock()

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

    # Ajustes de interface que exigem apenas HKCU; nunca mexe em proteções do Windows.
    _INTERFACE_ITEMS = {
        "startup_delay": (r"Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize",
                          "StartupDelayInMSec", 0, 4),
        "menu_delay": (r"Control Panel\Desktop", "MenuShowDelay", "100", 1),
    }

    # Ajustes individuais de privacidade do usuário atual com backup e restauração.
    # Não alteram Defender, Windows Update, Store, serviços ou política de telemetria.
    _PRIVACY_ITEMS = {
        "search_web": (r"Software\Policies\Microsoft\Windows\Explorer",
                       "DisableSearchBoxSuggestions", 1, 4),
        "feedback": (r"Software\Microsoft\Siuf\Rules",
                     "NumberOfSIUFInPeriod", 0, 4),
        "search_history": (r"Software\Microsoft\Windows\CurrentVersion\SearchSettings",
                           "IsDeviceSearchHistoryEnabled", 0, 4),
    }

    def _privacy_backup_path(self):
        return os.path.join(os.path.dirname(self._interface_backup_path()),
                            "privacy_backup.json")

    def _privacy_backups(self):
        try:
            with open(self._privacy_backup_path(), "r", encoding="utf-8") as handle:
                data = json.load(handle)
                return data if isinstance(data, dict) else {}
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return {}

    def _privacy_write_backup(self, data):
        path = self._privacy_backup_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temp = path + ".tmp"
        try:
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.remove(temp)

    def _privacy_read(self, name):
        path, value_name, _, data_type = self._PRIVACY_ITEMS[name]
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ) as key:
                value, actual_type = winreg.QueryValueEx(key, value_name)
                return {"exists": True, "value": value, "type": actual_type}
        except OSError:
            return {"exists": False, "value": None, "type": data_type}

    def privacy_status(self):
        output = {}
        if os.name != "nt" or winreg is None:
            for name in self._PRIVACY_ITEMS:
                output[name] = {"applied": None, "supported": False, "restorable": False}
            return output
        backups = self._privacy_backups()
        for name, (_, _, target, _) in self._PRIVACY_ITEMS.items():
            current = self._privacy_read(name)
            output[name] = {
                "applied": bool(current["exists"] and current["value"] == target),
                "supported": True,
                "restorable": name in backups,
            }
        return output

    def privacy_apply(self, name):
        if name not in self._PRIVACY_ITEMS or os.name != "nt" or winreg is None:
            return {"ok": False, "error": "Ajuste de privacidade indisponível."}
        with self._interface_lock:
            current = self._privacy_read(name)
            target = self._PRIVACY_ITEMS[name][2]
            if current["exists"] and current["value"] == target:
                return {"ok": True, "already": True}
            backups = self._privacy_backups()
            if name not in backups:
                backups[name] = current
                try:
                    self._privacy_write_backup(backups)
                except OSError:
                    return {"ok": False, "error": "Não foi possível criar backup."}
            path, value_name, target, value_type = self._PRIVACY_ITEMS[name]
            try:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                                        winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, value_name, 0, value_type, target)
            except OSError:
                return {"ok": False, "error": "O Windows não permitiu a alteração."}
            return {"ok": bool(self.privacy_status()[name]["applied"]),
                    "relogin": name in {"search_web", "search_history"}}

    def privacy_restore(self, name):
        if name not in self._PRIVACY_ITEMS or os.name != "nt" or winreg is None:
            return {"ok": False, "error": "Ajuste de privacidade indisponível."}
        with self._interface_lock:
            backups = self._privacy_backups()
            if name not in backups:
                return {"ok": False, "error": "Não há backup para restaurar."}
            path, value_name, _, _ = self._PRIVACY_ITEMS[name]
            previous = backups[name]
            try:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                                        winreg.KEY_SET_VALUE) as key:
                    if previous.get("exists"):
                        winreg.SetValueEx(key, value_name, 0,
                                          previous["type"], previous["value"])
                    else:
                        try:
                            winreg.DeleteValue(key, value_name)
                        except FileNotFoundError:
                            pass
                backups.pop(name, None)
                self._privacy_write_backup(backups)
                return {"ok": True, "relogin": name in {"search_web", "search_history"}}
            except (OSError, KeyError, TypeError):
                return {"ok": False, "error": "Não foi possível restaurar o ajuste."}


    # Controles de responsividade seguros por usuário (HKCU) e reversíveis.
    # Não modificam drivers, firmware, serviços, Defender ou proteções do Windows.
    _INPUT_ITEMS = {
        "mouse_acceleration": (
            (r"Control Panel\Mouse", "MouseSpeed", "0", 1),
            (r"Control Panel\Mouse", "MouseThreshold1", "0", 1),
            (r"Control Panel\Mouse", "MouseThreshold2", "0", 1),
        ),
        "background_capture": (
            (r"Software\Microsoft\Windows\CurrentVersion\GameDVR",
             "AppCaptureEnabled", 0, 4),
            (r"System\GameConfigStore", "GameDVR_Enabled", 0, 4),
        ),
    }

    def _input_backup_path(self):
        return os.path.join(os.path.dirname(self._interface_backup_path()),
                            "input_lag_backup.json")

    def _input_backups(self):
        try:
            with open(self._input_backup_path(), "r", encoding="utf-8") as handle:
                value = json.load(handle)
                return value if isinstance(value, dict) else {}
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return {}

    def _input_save_backups(self, data):
        path = self._input_backup_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def _input_read(self, entry):
        path, name, _, default_type = entry
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ) as key:
                value, value_type = winreg.QueryValueEx(key, name)
                return {"exists": True, "value": value, "type": value_type}
        except OSError:
            return {"exists": False, "value": None, "type": default_type}

    def _input_write(self, entry, data):
        path, name, _, _ = entry
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                                winreg.KEY_SET_VALUE) as key:
            if data["exists"]:
                winreg.SetValueEx(key, name, 0, data["type"], data["value"])
            else:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass

    def input_lag_status(self):
        supported = os.name == "nt" and winreg is not None
        backups = self._input_backups() if supported else {}
        result = {}
        for name, entries in self._INPUT_ITEMS.items():
            active = (all(self._input_read(e)["exists"]
                          and self._input_read(e)["value"] == e[2]
                          for e in entries) if supported else None)
            result[name] = {"supported": supported, "applied": active,
                            "restorable": name in backups}
        return result

    def input_lag_apply(self, name):
        if name not in self._INPUT_ITEMS or os.name != "nt" or winreg is None:
            return {"ok": False, "error": "Ajuste indisponível neste sistema."}
        with self._interface_lock:
            entries = self._INPUT_ITEMS[name]
            current = [self._input_read(e) for e in entries]
            if all(state["exists"] and state["value"] == e[2]
                   for state, e in zip(current, entries)):
                return {"ok": True, "already": True}
            backups = self._input_backups()
            if name not in backups:
                backups[name] = current
                try:
                    self._input_save_backups(backups)
                except OSError:
                    return {"ok": False, "error": "Não foi possível salvar backup."}
            written = []
            try:
                for entry, original in zip(entries, current):
                    self._input_write(entry, {"exists": True, "value": entry[2],
                                              "type": entry[3]})
                    written.append((entry, original))
            except OSError:
                for entry, original in reversed(written):
                    try:
                        self._input_write(entry, original)
                    except OSError:
                        pass
                return {"ok": False, "error": "Windows impediu a alteração; backup preservado."}
            return {"ok": bool(self.input_lag_status()[name]["applied"]),
                    "relogin": name == "mouse_acceleration"}

    def input_lag_restore(self, name):
        if name not in self._INPUT_ITEMS or os.name != "nt" or winreg is None:
            return {"ok": False, "error": "Ajuste indisponível neste sistema."}
        with self._interface_lock:
            backups = self._input_backups()
            states = backups.get(name)
            entries = self._INPUT_ITEMS[name]
            if not isinstance(states, list) or len(states) != len(entries):
                return {"ok": False, "error": "Backup não encontrado."}
            if not self.input_lag_status()[name]["applied"]:
                return {"ok": False, "error": "Ajuste mudou desde a aplicação. Backup mantido para revisão."}
            try:
                for entry, original in zip(entries, states):
                    self._input_write(entry, original)
            except (OSError, TypeError, KeyError):
                return {"ok": False, "error": "Restauração incompleta; backup preservado."}
            backups.pop(name, None)
            try:
                self._input_save_backups(backups)
            except OSError:
                return {"ok": False, "error": "Restaurado, mas não foi possível atualizar o registro de backup."}
            return {"ok": True, "relogin": name == "mouse_acceleration"}

    def open_driver_page(self, vendor):
        official = {
            "nvidia": "https://www.nvidia.com/pt-br/drivers/",
            "amd": "https://www.amd.com/pt/support/download/drivers.html",
        }
        if vendor not in official:
            return False
        try:
            return bool(webbrowser.open(official[vendor], new=2))
        except Exception:
            return False

    def _interface_backup_path(self):
        folder = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                              "LZPainel")
        return os.path.join(folder, "interface_backup.json")

    def _interface_load_backup(self):
        try:
            with open(self._interface_backup_path(), "r", encoding="utf-8") as handle:
                data = json.load(handle)
                return data if isinstance(data, dict) else {}
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return {}

    def _interface_save_backup(self, data):
        path = self._interface_backup_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temp = path + ".tmp"
        try:
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.remove(temp)

    def _interface_current(self, name):
        path, key, target, datatype = self._INTERFACE_ITEMS[name]
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ) as k:
                value, value_type = winreg.QueryValueEx(k, key)
                return {"exists": True, "value": value, "type": value_type}
        except OSError:
            return {"exists": False, "value": None, "type": datatype}

    def interface_status(self):
        if os.name != "nt" or winreg is None:
            return {"startup_delay": {"applied": None, "supported": False, "restorable": False},
                    "menu_delay": {"applied": None, "supported": False, "restorable": False},
                    "perf_counters": {"applied": None, "supported": False},
                    "kernel_ram": {"applied": None, "supported": False},
                    "memory_compression": {"applied": None, "supported": False}}
        backups = self._interface_load_backup()
        output = {}
        for name, (_, _, target, _) in self._INTERFACE_ITEMS.items():
            current = self._interface_current(name)
            output[name] = {"applied": current["exists"] and str(current["value"]) == str(target),
                            "supported": True, "restorable": name in backups}
        # Alterações em contadores, paginação do kernel ou compressão de memória
        # precisam de revisão manual: sem aplicação automática ou estado inventado.
        for key in ("perf_counters", "kernel_ram", "memory_compression"):
            output[key] = {"applied": None, "supported": False, "restorable": False}
        return output

    def interface_apply(self, name):
        if name not in self._INTERFACE_ITEMS or os.name != "nt" or winreg is None:
            return {"ok": False, "error": "Ajuste não disponível para aplicação automática."}
        with self._interface_lock:
            path, value_name, target, data_type = self._INTERFACE_ITEMS[name]
            before = self._interface_current(name)
            backups = self._interface_load_backup()
            if name not in backups:
                backups[name] = before
                try:
                    self._interface_save_backup(backups)
                except OSError:
                    return {"ok": False, "error": "Não foi possível salvar o backup."}
            try:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, value_name, 0, data_type, target)
                state = self.interface_status().get(name, {})
                return {"ok": bool(state.get("applied")), "reboot": name == "startup_delay"}
            except (OSError, TypeError):
                return {"ok": False, "error": "Não foi possível gravar a configuração."}

    def interface_restore(self, name):
        if name not in self._INTERFACE_ITEMS or os.name != "nt" or winreg is None:
            return {"ok": False, "error": "Ajuste não disponível."}
        with self._interface_lock:
            backups = self._interface_load_backup()
            if name not in backups:
                return {"ok": False, "error": "Não existe backup para restaurar."}
            old = backups[name]
            path, value_name, _, _ = self._INTERFACE_ITEMS[name]
            try:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
                    if old.get("exists"):
                        winreg.SetValueEx(key, value_name, 0, old["type"], old["value"])
                    else:
                        try:
                            winreg.DeleteValue(key, value_name)
                        except FileNotFoundError:
                            pass
                backups.pop(name, None)
                self._interface_save_backup(backups)
                return {"ok": True, "reboot": name == "startup_delay"}
            except (OSError, KeyError, TypeError):
                return {"ok": False, "error": "Não foi possível restaurar a configuração."}


    # Game Boost: mudanças explícitas, reversíveis e limitadas às configurações de usuário.
    # Não altera EXEs, anti-cheat, Defender, Windows Update ou saves dos jogos.
    _GB_IDS = ("valorant", "minecraft", "fortnite", "bluestacks", "discord")
    _GB_OPTIONS = {
        "valorant": {"bUseVSync": "False", "sg.ShadowQuality": "0",
                     "sg.PostProcessQuality": "0", "sg.EffectsQuality": "0"},
        "minecraft": {"renderDistance": "8", "simulationDistance": "6",
                      "particles": "1", "entityShadows": "false",
                      "biomeBlendRadius": "0"},
        "fortnite": {"bUseVSync": "False", "bMotionBlur": "False",
                     "sg.ShadowQuality": "0", "sg.PostProcessQuality": "0",
                     "sg.EffectsQuality": "0"},
    }

    def _gb_root(self):
        folder = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                              "LZPainel", "GameBoost")
        os.makedirs(folder, exist_ok=True)
        return folder

    def _gb_manifest(self):
        path = os.path.join(self._gb_root(), "manifest.json")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
                return data if isinstance(data, dict) else {}
        except (FileNotFoundError, ValueError, OSError, TypeError):
            return {}

    def _gb_write_manifest(self, entries):
        folder = self._gb_root()
        fd, tmp = tempfile.mkstemp(prefix="manifest_", suffix=".json", dir=folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(entries, handle, ensure_ascii=False, indent=2)
            os.replace(tmp, os.path.join(folder, "manifest.json"))
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    @staticmethod
    def _gb_sha(path):
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()

    @staticmethod
    def _gb_existing(path):
        return path if path and os.path.isfile(path) else ""

    def _gb_path_for(self, game_id):
        local = os.environ.get("LOCALAPPDATA", "")
        roaming = os.environ.get("APPDATA", "")
        if game_id == "minecraft":
            return self._gb_existing(os.path.join(roaming, ".minecraft", "options.txt"))
        if game_id == "fortnite":
            for leaf in ("WindowsClient", "Windows"):
                path = os.path.join(local, "FortniteGame", "Saved", "Config", leaf,
                                    "GameUserSettings.ini")
                if os.path.isfile(path):
                    return path
            return ""
        if game_id == "valorant":
            root = os.path.join(local, "VALORANT", "Saved", "Config")
            if not os.path.isdir(root):
                return ""
            paths = glob.glob(os.path.join(root, "**", "GameUserSettings.ini"),
                              recursive=True)
            root_real = os.path.normcase(os.path.realpath(root))
            matches = []
            for path in paths:
                try:
                    if (os.path.commonpath((root_real, os.path.normcase(os.path.realpath(path))))
                            == root_real and os.path.isfile(path)):
                        matches.append(path)
                except (OSError, ValueError):
                    continue
            return max(matches, key=os.path.getmtime) if matches else ""
        if game_id == "bluestacks":
            program_dirs = [os.environ.get("ProgramFiles", ""),
                            os.environ.get("ProgramFiles(x86)", "")]
            for root in program_dirs:
                for leaf in ("BlueStacks_nxt", "BlueStacks"):
                    path = os.path.join(root, leaf, "HD-Player.exe")
                    if os.path.isfile(path):
                        return path
            return ""
        if game_id == "discord":
            root = os.path.join(local, "Discord")
            matches = glob.glob(os.path.join(root, "app-*", "Discord.exe"))
            return max(matches, key=os.path.getmtime) if matches else ""
        return ""

    @staticmethod
    def _gb_running(game_id):
        if os.name != "nt":
            return False
        names = {
            "valorant": {"valorant-win64-shipping.exe"},
            "minecraft": {"javaw.exe"},
            "fortnite": {"fortniteclient-win64-shipping.exe", "fortniteclient-win64-shipping_eac.exe"},
            "bluestacks": {"hd-player.exe"},
            "discord": {"discord.exe"},
        }.get(game_id, set())
        try:
            return any((p.info.get("name") or "").lower() in names
                       for p in psutil.process_iter(["name"]))
        except (OSError, psutil.Error):
            return False

    @staticmethod
    def _gb_patch_text(raw, game_id):
        """Retorna bytes modificados e nomes efetivamente alterados, preservando demais linhas."""
        encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
        text = raw.decode(encoding)
        updates = Api._GB_OPTIONS[game_id]
        altered = []
        for key, value in updates.items():
            sep = ":" if game_id == "minecraft" else "="
            pattern = re.compile(r"(?m)^(\s*" + re.escape(key)
                                 + r"\s*" + re.escape(sep) + r"\s*)([^\r\n]*)$")
            def patch(match):
                if match.group(2).strip() != value:
                    altered.append(key)
                return match.group(1) + value
            text = pattern.sub(patch, text)
        return text.encode(encoding), list(dict.fromkeys(altered))

    def game_profiles(self):
        entries = self._gb_manifest()
        out = {}
        for game_id in self._GB_IDS:
            path = self._gb_path_for(game_id)
            entry = entries.get(game_id) or {}
            applied = False
            if entry.get("path") == path and path:
                try:
                    if entry.get("kind") == "file":
                        applied = self._gb_sha(path) == entry.get("after_sha")
                    elif entry.get("kind") == "gpu" and os.name == "nt" and winreg:
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\DirectX\UserGpuPreferences") as key:
                            val, _ = winreg.QueryValueEx(key, path)
                            applied = val == entry.get("value")
                except (OSError, ValueError):
                    pass
            out[game_id] = {"found": bool(path), "path": path, "applied": applied,
                            "restorable": bool(entry), "running": self._gb_running(game_id),
                            "kind": "arquivo" if game_id in self._GB_OPTIONS else "gráficos do Windows"}
        return out

    def game_optimize(self, game_id):
        if game_id not in self._GB_IDS:
            return {"ok": False, "error": "Perfil de jogo inválido."}
        if self._gb_running(game_id):
            return {"ok": False, "error": "Feche o jogo ou aplicativo antes de aplicar o perfil."}
        path = self._gb_path_for(game_id)
        if not path:
            return {"ok": False, "error": "Instalação ou configuração não encontrada."}
        entries = self._gb_manifest()
        if game_id in entries:
            return {"ok": False, "error": "Já existe um backup desse perfil. Restaure antes de reaplicar."}
        if game_id in self._GB_OPTIONS:
            try:
                with open(path, "rb") as handle:
                    original = handle.read()
                patched, fields = self._gb_patch_text(original, game_id)
                if not fields:
                    return {"ok": False, "error": "Sem configurações compatíveis para alterar neste arquivo."}
                fd, backup = tempfile.mkstemp(prefix=game_id+"_",suffix=".bak",
                                               dir=self._gb_root())
                with os.fdopen(fd, "wb") as handle:
                    handle.write(original)
                temp = path + ".lztemp"
                try:
                    with open(temp, "wb") as handle:
                        handle.write(patched)
                    os.replace(temp, path)
                finally:
                    if os.path.exists(temp):
                        os.remove(temp)
                entry = {"kind": "file", "path": path, "backup": backup,
                         "before_sha": hashlib.sha256(original).hexdigest(),
                         "after_sha": hashlib.sha256(patched).hexdigest(),
                         "when": time.strftime("%Y-%m-%d %H:%M")}
                entries[game_id] = entry
                try:
                    self._gb_write_manifest(entries)
                except OSError:
                    with open(path, "wb") as handle:
                        handle.write(original)
                    raise
                return {"ok": True, "changes": fields, "restorable": True,
                        "summary": "Configuração salva com backup: "+", ".join(fields)}
            except (OSError, ValueError, UnicodeError) as exc:
                return {"ok": False, "error": "Não foi possível modificar a configuração: "+str(exc)}
        if os.name != "nt" or not winreg:
            return {"ok": False, "error": "Preferência gráfica disponível apenas no Windows."}
        keypath = r"Software\Microsoft\DirectX\UserGpuPreferences"
        preference = "GpuPreference=2;" if game_id == "bluestacks" else "GpuPreference=1;"
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, keypath, 0,
                                    winreg.KEY_READ | winreg.KEY_WRITE) as key:
                try:
                    original, original_type = winreg.QueryValueEx(key, path)
                    existed = True
                except FileNotFoundError:
                    original, original_type, existed = "", winreg.REG_SZ, False
                if existed and original == preference:
                    return {"ok": False, "error": "A preferência gráfica já está aplicada."}
                winreg.SetValueEx(key, path, 0, winreg.REG_SZ, preference)
            entries[game_id] = {"kind": "gpu", "path": path,
                                "existed": existed, "original": original,
                                "original_type": original_type, "value": preference,
                                "when": time.strftime("%Y-%m-%d %H:%M")}
            try:
                self._gb_write_manifest(entries)
            except OSError:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, keypath, 0,
                                        winreg.KEY_SET_VALUE) as key:
                    if existed:
                        winreg.SetValueEx(key, path, 0, original_type, original)
                    else:
                        winreg.DeleteValue(key, path)
                raise
            return {"ok": True, "changes": ["Preferência gráfica do Windows"],
                    "restorable": True,
                    "summary": ("Alto desempenho" if game_id == "bluestacks"
                                else "Economia de energia") + " configurado para o aplicativo."}
        except OSError as exc:
            return {"ok": False, "error": "Não foi possível configurar a GPU: "+str(exc)}

    def game_restore(self, game_id):
        if game_id not in self._GB_IDS:
            return {"ok": False, "error": "Perfil inválido."}
        entries = self._gb_manifest()
        entry = entries.get(game_id)
        if not entry:
            return {"ok": False, "error": "Não há backup para restaurar."}
        path = entry.get("path", "")
        if path != self._gb_path_for(game_id):
            return {"ok": False, "error": "O caminho do aplicativo mudou; verifique o backup manualmente."}
        if self._gb_running(game_id):
            return {"ok": False, "error": "Feche o aplicativo antes de restaurar."}
        try:
            if entry["kind"] == "file":
                backup = entry.get("backup", "")
                root = os.path.realpath(self._gb_root())
                if (not backup or os.path.commonpath((root,os.path.realpath(backup))) != root
                        or not os.path.isfile(backup)):
                    return {"ok": False, "error": "Arquivo de backup não encontrado."}
                if self._gb_sha(path) != entry.get("after_sha"):
                    return {"ok": False, "error": "Arquivo alterado depois do perfil. O backup foi preservado."}
                shutil.copy2(backup, path)
            else:
                if os.name != "nt" or not winreg:
                    return {"ok": False, "error": "Restauração disponível somente no Windows."}
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\DirectX\UserGpuPreferences",0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as key:
                    try:
                        current, _ = winreg.QueryValueEx(key, path)
                    except FileNotFoundError:
                        current = None
                    if current != entry.get("value"):
                        return {"ok": False, "error": "Preferência alterada depois do perfil; backup preservado."}
                    if entry.get("existed"):
                        winreg.SetValueEx(key,path,0,entry.get("original_type",winreg.REG_SZ),
                                          entry.get("original",""))
                    else:
                        winreg.DeleteValue(key,path)
            del entries[game_id]
            self._gb_write_manifest(entries)
            return {"ok": True, "summary": "Configuração anterior restaurada."}
        except (OSError, ValueError, KeyError) as exc:
            return {"ok": False, "error": "Falha ao restaurar: "+str(exc)}

    def open_community(self):
        """Abre apenas o convite oficial configurado da comunidade, no navegador externo."""
        try:
            return bool(webbrowser.open("https://discord.gg/efdF2Cfrb", new=2))
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
