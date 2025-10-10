#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЭТАП 1: СБОР ВЫВОДОВ КОМАНД С УСТРОЙСТВ (БЕЗ ИНВЕНТАРЯ)

Что делает этот скрипт:
  • Принимает цели в двух формах:
      --targets  IP/имена через пробел
      --cidr     подсети в формате CIDR (например, 10.20.96.0/24)
    Если указаны оба варианта — объединяем.
  • Подключается к каждому адресу по SSH; при неуспехе — пробует Telnet.
  • Для каждого успешного хоста выполняет набор «диагностических» команд
    (под разные вендоры) и сохраняет все выводы в один файл:
      data/raw/<IP>.txt
  • Каждая команда в файле помечается как:
      $ <команда>
      <сырой вывод>
    Это упростит последующий парсинг.

Зачем столько комментариев:
  • Сейчас наша цель — сделать основу максимально прозрачной,
    чтобы в любой момент можно было:
      - быстро добавить новый вендор/тип,
      - поменять перечень команд,
      - расширить логи/обработку ошибок,
      - интегрировать ntc-templates/TextFSM на следующем этапе.

Требования к окружению:
  • Python 3.9+
  • pip install netmiko paramiko rich tqdm
  • Переменные окружения (необязательно, можно ввести руками при старте):
      NET_USER, NET_PASS, NET_ENABLE
  • Запуск примеров:
      python stage1_collect.py --cidr 10.20.96.0/24 10.20.97.0/24
      python stage1_collect.py --targets 10.20.96.10 10.20.96.11

Важно:
  • В рамках первой версии мы НЕ используем внешний инвентарный файл.
    Всё минимально: цели приходят из CLI параметров.
  • Мы умышленно сохраняем сырые выводы без структурирования — это осознанный
    выбор, т.к. Этап 2 займётся парсингом (в т.ч. через TextFSM/ntc-templates).
"""

from __future__ import annotations

import argparse
import json
import getpass
import ipaddress
import os

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, List

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
import socket
# Внешняя зависимость: netmiko — библиотека для SSH/Telnet на сетевые устройства
# Документация: https://github.com/ktbyers/netmiko
from netmiko import ConnectHandler
try:  # SSH autodetect (best-effort)
    from netmiko.ssh_autodetect import SSHDetect  # type: ignore
except Exception:  # pragma: no cover
    SSHDetect = None  # fallback without autodetect
def is_port_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

# -----------------------
# НАСТРОЙКИ И КОНСТАНТЫ
# -----------------------

# Папка, куда пишем сырые выводы
DATA_RAW = Path("data") / "raw"
COLLECT_CFG_DIR = Path("config") / "collect"

# Перечень команд под разные device_type.
# Примечания:
#  - ключи соответствуют типам Netmiko (например, "cisco_ios", "cisco_ios_telnet")
#  - если нужного ключа нет, используем "generic"
#  - "pre_enable": если True — пытаемся выполнить enable() после входа
COMMANDS_BY_TYPE: Dict[str, Dict] = {
    "cisco_ios": {
        "pre_enable": True,
        "commands": [
            "show running-config",
            "show version",
            # CDP/LLDP — для топологии (Этап 2 будет вытягивать соседей)
            "show cdp neighbors detail",
            "show lldp neighbors detail",
            # Порты (статус/VLAN) — пригодится для подписей и фильтрации
            "show interface status",
        ],
    },
    # Для Telnet-устройств Cisco Netmiko ожидает отдельный тип:
    "cisco_ios_telnet": {"extends": "cisco_ios"},
    # HP ProCurve / ArubaOS-Switch
    "hp_procurve": {
        "pre_enable": False,
        "commands": [
            "show running-config",
            "show system-information",
            # LLDP (у ProCurve другой синтаксис)
            "show lldp info remote-device detail",
            # Сводка по интерфейсам
            "show interfaces brief",
        ],
    },
    # Иногда для Telnet под ProCurve используется тот же тип с суффиксом,
    # но не во всех версиях Netmiko есть явный *_telnet. Оставим маппинг на будущее.
    "hp_procurve_telnet": {"extends": "hp_procurve"},
    # Juniper JunOS — команды вида "show ...", конфиги удобно в display set
    "juniper_junos": {
        "pre_enable": False,
        "commands": [
            "show configuration | display set",
            "show version",
            "show lldp neighbors detail",
            "show interfaces terse",
            "show chassis hardware",
        ],
    },
    "juniper_junos_telnet": {"extends": "juniper_junos"},
    # Generic — на случай «чего-то неизвестного», лучше чем ничего
    "generic": {
        "pre_enable": False,
        "commands": [
            "show running-config",
            "show lldp neighbors detail",
        ],
    },
    "generic_telnet": {"extends": "generic"},
}

# Optional mapping from Netmiko autodetected device types to our profiles
NETMIKO_TO_PROFILE = {
    "cisco_ios": "cisco_ios",
    "hp_procurve": "hp_procurve",
    "aruba_procurve": "hp_procurve",
    "juniper_junos": "juniper_junos",
    "juniper": "juniper_junos",
    "mikrotik_routeros": "generic",  # TODO: add dedicated profile if needed
    "huawei": "generic",
    "dlink_ds": "generic",
}

# Порядок попыток: сначала SSH, затем Telnet, по вендорам
# В реальности вы можете ограничить список под свой зоопарк устройств.
DEVICE_TRY_ORDER = [
    "cisco_ios",
    "hp_procurve",
    "juniper_junos",
    "generic",
]

console = Console()


# ---------------
# ВСПОМОГАТЕЛЬНОЕ
# ---------------

def ensure_dirs() -> None:
    """Гарантируем наличие каталога для сырых артефактов."""
    DATA_RAW.mkdir(parents=True, exist_ok=True)


def env(name: str, default: str = "") -> str:
    """Короткий помощник для чтения переменных окружения."""
    return os.environ.get(name, default)


def _load_external_profile(dt_base: str) -> Dict:
    """Load command profile override from config/collect.

    Supports JSON file with keys {"pre_enable": bool, "commands": [..]}
    or plain .txt with one command per line (non-empty, not starting with '#').
    """
    try:
        # prefer JSON
        js = (COLLECT_CFG_DIR / f"{dt_base}.json")
        if js.exists():
            raw = json.loads(js.read_text(encoding="utf-8"))
            prof: Dict[str, object] = {}
            if isinstance(raw, dict):
                if isinstance(raw.get("pre_enable"), bool):
                    prof["pre_enable"] = raw["pre_enable"]
                if isinstance(raw.get("commands"), list):
                    prof["commands"] = [str(x) for x in raw["commands"] if str(x).strip()]
            return prof
        # fallback to .txt
        txt = (COLLECT_CFG_DIR / f"{dt_base}.txt")
        if txt.exists():
            cmds: List[str] = []
            pre_enable = None
            for line in txt.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = line.strip()
                if not s or s.startswith("#"):
                    # allow directive like: # pre_enable=true
                    if s.lower().startswith("# pre_enable="):
                        val = s.split("=", 1)[1].strip().lower()
                        pre_enable = (val in ("1", "true", "yes", "on"))
                    continue
                cmds.append(s)
            prof2: Dict[str, object] = {}
            if pre_enable is not None:
                prof2["pre_enable"] = bool(pre_enable)
            if cmds:
                prof2["commands"] = cmds
            return prof2
    except Exception:
        pass
    return {}


def profile_for_device_type(device_type: str) -> Dict:
    """Return merged command profile for a device_type with external overrides."""
    base = device_type.replace("_telnet", "")
    prof = dict(COMMANDS_BY_TYPE.get(device_type, COMMANDS_BY_TYPE.get(base, COMMANDS_BY_TYPE["generic"])))
    override = _load_external_profile(base)
    if override.get("pre_enable") is not None:
        prof["pre_enable"] = bool(override["pre_enable"])  # type: ignore[index]
    if override.get("commands"):
        prof["commands"] = list(override["commands"])  # type: ignore[index]
    return prof


def iter_targets(seed_ips: Iterable[str], cidrs: Iterable[str]) -> Iterable[str]:
    """
    Генератор адресов:
      - сперва вернёт явно заданные IP/имена (seed_ips),
      - затем развернёт все подсети из cidrs и вернёт host-адреса.
    Дубликаты отфильтровываются.
    """
    seen = set()
    # Прямые цели
    for t in seed_ips:
        t = t.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        yield t
    # Подсети
    for c in cidrs:
        c = c.strip()
        if not c:
            continue
        net = ipaddress.ip_network(c, strict=False)
        for ip in net.hosts():
            s = str(ip)
            if s not in seen:
                seen.add(s)
                yield s


def merge_commands_for(device_type: str) -> Dict:
    """
    Возвращает профиль команд для конкретного device_type,
    разворачивая 'extends' если он задан.
    """
    prof = profile_for_device_type(device_type)
    if "extends" in prof:
        base = profile_for_device_type(prof["extends"])  # type: ignore[index]
        merged = dict(base)
        merged.update({k: v for k, v in prof.items() if k != "extends"})
        return merged
    return prof


# -----------------------
# ОСНОВНАЯ РАБОЧАЯ ЛОГИКА
# -----------------------

def gather_one(ip: str, creds: Dict[str, str]) -> Dict:
    """
    Пытаемся подключиться к адресу ip, перебирая device_type и транспорт (SSH→Telnet).
    При успехе — выполняем команды и сохраняем выводы в data/raw/<ip>.txt.

    Возвращаем краткий итог:
      {"ip": "...", "status": "ok", "device_type": "..."}  либо
      {"ip": "...", "status": "fail", "errors": ["...","..."]}
    """
    errors: List[str] = []

    # Autodetect SSH device_type (if possible) to select proper command profile
    primary_dt: str | None = None
    if SSHDetect is not None and is_port_open(ip, 22, float(env("CONNECT_TIMEOUT", "3"))):
        try:
            guesser = SSHDetect(
                device_type="autodetect",
                host=ip,
                username=creds["user"],
                password=creds["pass"],
                timeout=float(env("AUTH_TIMEOUT", "20")),
            )
            best = guesser.autodetect()
            if best:
                primary_dt = NETMIKO_TO_PROFILE.get(best, best)
        except Exception as e:
            errors.append(f"autodetect_ssh: {e}")

    # Compose try-order: detected first, then defaults
    order: List[str] = []
    if primary_dt:
        order.append(primary_dt)
    order.extend([dt for dt in DEVICE_TRY_ORDER if dt not in order])

    # Проходим по списку кандидатов (вендоров)
    for base_dt in order:
        # Две попытки: сначала SSH, затем Telnet
        for transport in ("ssh", "telnet"):
            dt = base_dt if transport == "ssh" else f"{base_dt}_telnet"
            profile = merge_commands_for(dt)
            commands = profile.get("commands", ["show running-config"])
            pre_enable = profile.get("pre_enable", False)

            # Готовим параметры для Netmiko
            params = {
                "host": ip,
                "username": creds["user"],
                "password": creds["pass"],
                "device_type": dt,
                # Явно задаём таймауты (берём из env, которое заполнили из аргументов CLI)
                "conn_timeout": int(env("CONNECT_TIMEOUT", "12")),
                "auth_timeout": int(env("AUTH_TIMEOUT", "20")),
                "banner_timeout": int(env("CONNECT_TIMEOUT", "12")),
                "timeout": int(env("AUTH_TIMEOUT", "20")),
                "session_timeout": max(int(env("CONNECT_TIMEOUT", "12")), int(env("AUTH_TIMEOUT", "20"))) + 2,
            }
            if creds.get("secret"):
                params["secret"] = creds["secret"]

            try:
                # 1) Подключение
                conn = ConnectHandler(**params)

                # 2) enable режим (если нужен и задан secret)
                if pre_enable and creds.get("secret"):
                    try:
                        conn.enable()
                    except Exception as ee:
                        # Не критично — продолжаем без enable
                        errors.append(f"{dt}: enable() failed: {ee}")

                # 3) Выполнить команды последовательно и собрать куски
                chunks: List[str] = []
                for cmd in commands:
                    try:
                        out = conn.send_command(cmd, read_timeout=60)
                        # Маркеры команд — для удобного дальнейшего парсинга
                        chunks.append("\n\n$ " + cmd + "\n" + (out or ""))
                    except Exception as e_cmd:
                        chunks.append("\n\n$ " + cmd + "\n" + f"[ERROR executing command: {e_cmd}]")

                # 4) Сохранить в файл по IP (hostname вытащим позже на Этапе 2)
                ensure_dirs()
                out_path = DATA_RAW / f"{ip}.txt"
                out_path.write_text("\n".join(chunks), encoding="utf-8", errors="ignore")

                # 5) Закрыть сессию и вернуть успех
                try:
                    conn.disconnect()
                except Exception:
                    pass

                return {"ip": ip, "status": "ok", "device_type": dt}
            except Exception as e:
                # Копим ошибки и пробуем следующий тип/транспорт
                errors.append(f"{dt}: {e}")

    # Если сюда дошли — все попытки провалились
    return {"ip": ip, "status": "fail", "errors": errors[:4]}  # срез, чтобы не раздувать лог


def main() -> None:
    """
    Точка входа: читаем параметры CLI, спрашиваем креды (или берём из env),
    запускаем параллельный сбор и печатаем сводную таблицу.
    """
    parser = argparse.ArgumentParser(
        description="Этап 1: сбор выводов команд по SSH/Telnet без инвентарного файла."
    )
    parser.add_argument("--targets", nargs="*", default=[], help="Список IP/имён (через пробел)")
    parser.add_argument("--cidr", nargs="*", default=[], help="Список подсетей в формате CIDR")
    parser.add_argument("--max-workers", type=int, default=int(env("MAX_WORKERS", "20")),
                        help="Количество параллельных потоков (по умолчанию из env MAX_WORKERS или 20)")
    parser.add_argument("--conn-timeout", type=float, default=3.0,
                        help="TCP connect timeout (sec) для Netmiko")
    parser.add_argument("--auth-timeout", type=float, default=5.0,
                        help="Auth/login timeout (sec) для Netmiko")
    parser.add_argument("--tcp-timeout", type=float, default=1.0, help="TCP check timeout (sec) для предварительной проверки портов 22/23")
    
    args = parser.parse_args()
    os.environ["CONNECT_TIMEOUT"] = str(int(args.conn_timeout))
    os.environ["AUTH_TIMEOUT"] = str(int(args.auth_timeout))

    # Креды: берём из окружения или спрашиваем
    user = env("NET_USER") or input("Username: ")
    pwd = env("NET_PASS") or getpass.getpass("Password: ")
    secret = env("NET_ENABLE", "")

    creds = {"user": user, "pass": pwd, "secret": secret}

    # Итоговый набор целей
    targets = list(iter_targets(args.targets, args.cidr))
    # --- Исключаем из скана IP и подсети из EXCLUDE_IPS (csv) ---
    # Пример: EXCLUDE_IPS=10.12.0.26,10.12.0.10,10.12.0.0/24,10.10.0.0/24
    _excl_raw = os.environ.get("EXCLUDE_IPS", "")
    _exclude_specs = [x.strip() for x in _excl_raw.split(",") if x.strip()]

    _exclude_networks = []
    _exclude_ips = set()
    import ipaddress

    for spec in _exclude_specs:
        try:
            if "/" in spec:
                _exclude_networks.append(ipaddress.ip_network(spec, strict=False))
            else:
                # «Голый» сетевой адрес → считаем /24 (а если x.y.0.0 — /16)
                parts = spec.split(".")
                if len(parts) == 4 and parts[2] == "0" and parts[3] == "0":
                    _exclude_networks.append(ipaddress.ip_network(f"{parts[0]}.{parts[1]}.0.0/16", strict=False))
                elif len(parts) == 4 and parts[3] == "0":
                    _exclude_networks.append(ipaddress.ip_network(f"{parts[0]}.{parts[1]}.{parts[2]}.0/24", strict=False))
                else:
                    _exclude_ips.add(str(ipaddress.ip_address(spec)))
        except Exception as e:
            console.print(f"[yellow]Warning: bad EXCLUDE_IPS entry '{spec}': {e}[/]")

    if _exclude_networks or _exclude_ips:
        before = len(targets)
        filtered: List[str] = []
        for t in targets:
            try:
                ip = ipaddress.ip_address(t)
            except Exception:
                # если вдруг t не IP — пропускаем (не должно быть)
                continue

            if str(ip) in _exclude_ips:
                continue

            skip = False
            for net in _exclude_networks:
                if ip in net:
                    skip = True
                    break
            if skip:
                continue

            filtered.append(str(ip))

        targets = filtered
        console.print(f"[yellow]Excluded {_exclude_specs} — {before - len(targets)} host(s) removed from scan[/]")
    # --- конец блока исключений ---
# если список пуст — ничего не печатаем и не трогаем targets
    if not targets:
        console.print("[red]Не задано ни одной цели (--targets/--cidr). Завершение.[/]")
        return

    console.print(f"[bold]Всего потенциальных целей:[/] {len(targets)}")
    # Быстрый отбор по открытым портам 22/23 — чтобы не залипать на тайм-аутах Netmiko
    # Параллельный отбор по открытым портам 22/23 — гораздо быстрее на больших списках
    from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed

    def _check_host(h: str) -> str | None:
        try:
            if is_port_open(h, 22, args.tcp_timeout) or is_port_open(h, 23, args.tcp_timeout):
                return h
        except Exception:
            return None
        return None

    live: List[str] = []
    # Ограничиваем параллельность для проверки портов (не обязательно равна args.max_workers)
    tcp_workers = min(64, max(4, args.max_workers))
    with ThreadPoolExecutor(max_workers=tcp_workers) as _ex:
        futs = { _ex.submit(_check_host, h): h for h in targets }
        for fut in _as_completed(futs):
            try:
                res = fut.result()
                if res:
                    live.append(res)
            except Exception:
                # игнорируем единичные ошибки проверки
                continue

    console.print(f"[bold]Хостов с открытым 22/23:[/] {len(live)}")
    if not live:
        console.print("[yellow]Нет хостов с открытым 22/23. Завершение скана.[/]")
        return
    ensure_dirs()
    total = len(live)

    # Прогресс-бар
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        transient=False,
    )
    task_id = progress.add_task("Сбор CLI", total=total)

    results: List[Dict] = []
    with progress:
        with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
            futs = {ex.submit(gather_one, ip, creds): ip for ip in live}
            done = 0
            for fut in as_completed(futs):
                res = fut.result()
                results.append(res)
                done += 1
                progress.update(task_id, completed=done)

                # Короткая строка статуса (видна и при редиректе в лог)
                ip = res.get("ip") or res.get("host") or "?"
                st = res.get("status", "unknown")
                info = res.get("device_type") or res.get("info") or ""
                console.print(f"[dim]{done}/{total}[/] {ip}: {st} {info}")

    # Сводная таблица по итогам
    table = Table(title="Stage 1: Collection results")
    table.add_column("IP/Host")
    table.add_column("Status")
    table.add_column("Info / Errors")

    ok_count = 0
    for r in results:
        if r["status"] == "ok":
            ok_count += 1
            table.add_row(r["ip"], "[green]ok[/]", r.get("device_type", ""))
        else:
            info = "; ".join(r.get("errors", []))
            if len(info) > 120:
                info = info[:117] + "..."
            table.add_row(r["ip"], "[red]fail[/]", info)

    console.print(table)
    console.print(f"[bold]Успешно собраны устройства:[/] {ok_count} / {len(results)}")
    console.print(f"[bold]Артефакты:[/] {DATA_RAW.resolve()}")

if __name__ == "__main__":
    main()
