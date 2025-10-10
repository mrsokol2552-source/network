<<<<<<< HEAD
# network
=======
# Mermaid NetDocs

Автогенерация сетевых диаграмм **Mermaid** из инвентаря (и при желании — из CLI через **TextFSM**).  
Проект мультивендорный (Cisco IOS/IOS-XE, Eltex MES, Qtech, D-Link, Huawei VRP, MikroTik).

## Структура

mermaid-netdocs/
config/config.json
standards/mermaid_style.md
templates/textfsm/{cisco_ios,eltex_mes,qtech,dlink,huawei_vrp,mikrotik}/example.template
data/input/inventory.json
data/output/network.mmd
data/output/logs/{parsed_textfsm.json,normalized.json}
src/parsers/{textfsm_loader.py,normalize.py}
src/renderers/mermaid_writer.py
src/main.py
scripts/make_example.bat
tests/test_normalize_and_render_smoke.py
>>>>>>> be8afee (Initial commit)
