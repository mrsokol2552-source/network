# Дополнение к проекту: **Государства, Дипломатия, Редкости Исследований, Аномалии и Автоматизация**
Версия: 1.0 • Ядро: Unity (C#) • Архитектура: Domain/Data/Application/AI/Presentation/Infrastructure  
Совместимость: off‑screen LOD‑симуляция, EventBus, сохранения JSON, Pathfinding

> Цель: оформить в рабочий план доп. подсистемы — несколько государств с дипломатией (посольства/союзы/слияние), пересобранное древо исследований (обычные/редкие/аномальные) и автоматизация процессов через серверные/ядра.

---

## 0) Коротко (TL;DR)
- **Государства (States)**: старт за выбранное государство; уровни отношений → *Нет контакта* → *Посольство* → *Союз* → *(возможное) Слияние*.
- **Видимость/интел**:  
  - Нет контакта/вражда — **AI не “видит”** юниты/постройки других (собственный FoW).  
  - Посольство — **видит юниты/постройки**, **без** экономики/задач.  
  - Союз — видит **всё** (вкл. экономику и задачи), но **контролирует только свои** юниты.
- **Слияние**: ежедневно малая вероятность p, растущая со временем союза; при слиянии управление передаётся **одному AI**; игрок остаётся лидером своей стороны.
- **Исследования**: ветки с “одним видимым шагом”; редкость: **Обычные / Редкие / Аномальные**. Шанс редких зависит от **качества исследований** (скрытый показатель зданий). Стоимость растёт на **10–15%** за шаг.
- **Здания науки**: два типа апгрейда — **количественный** (RP↑) и **качественный** (QP↑). Игрок **не знает** точный шанс редких.
- **Аномалии**: доступны только при наличии **содержания заражённых** и **команд поимки**; образцы тратятся в ходе исследований; требуется **автоматизация** цикла “поимка→доставка→исследование”.
- **Автоматизация**: **Серверные** здания дают **вычислительные единицы (CU)**; **Ядро автоматизации** берёт под контроль **один** объект (отряд/здание), потребляя **много энергии** и CU; ядро выполняет процесс целиком.

---

## 1) Domain (модели и правила)

### 1.1 Сущности
```csharp
public enum IntelAccess { None, UnitsAndBuildings, Full }        // уровни доступа
public enum RelationKind { None, Hostile, Embassy, Alliance }     // стадия отношений
public enum ResearchRarity { Common, Rare, Anomalous }

public sealed record StateId(string Value);
public sealed record SectorId(int X, int Y);

public sealed class State
{
    public StateId Id;
    public string Title;
    public Dictionary<StateId, Relation> Relations = new();
    public IntelLayer Intel;                   // знание о мире (своё FoW)
    public EconomySnapshot Economy;            // свои запасы
    public ResearchProgress Research;          // прогресс по веткам/стоимость
    public AutomationNetwork Automation;       // доступные CU и привязанные ядра
}

public sealed class Relation
{
    public RelationKind Kind;                  // None/Hostile/Embassy/Alliance
    public float DaysInAlliance;               // растёт только в Alliance
    public float Stability;                    // 0..1 (доверие, общие цели, история)
}

public sealed class IntelLayer               // "карта знаний" государства
{
    // Что известно о секторах/юнитах/постройках других государств
    public IntelAccess AccessTo(StateId other);
    public KnownUnits GetKnownUnits(SectorId s, StateId other);
    public KnownBuildings GetKnownBuildings(SectorId s, StateId other);
    public KnownEconomy GetKnownEconomy(StateId other); // только при Full
}

public sealed class ResearchProgress
{
    public Dictionary<string, Branch> Branches;  // "Экономика/Добыча" и пр.
    public int TotalSteps;                       // для инфляции стоимости
    public float CostMultiplier;                 // (1+r)^(n)
    public float QualityScore;                   // агрегат QP/RP (скрыт от игрока)
}

public sealed class Branch
{
    public string Id;               // "economy.extraction"
    public int Completed;           // сколько пройдено шагов
    public ResearchDef Current;     // единственный видимый шаг
}

public sealed class ResearchDef
{
    public string Id;
    public string BranchId;
    public ResearchRarity Rarity;   // Common/Rare/Anomalous
    public float BaseCostRP;        // базовая стоимость
    public string[] PrereqIds;      // зависимости
    public string[] RequiresAssets; // напр. "ContainmentLab", "CaptureTeam"
}
```

### 1.2 Формулы и правила
- **Интел‑доступ:**  
  `None  → (ничего)`;  
  `Embassy → Units+Buildings` (позиции/типы/здоровье, без экономики/задач);  
  `Alliance → Full` (вкл. экономики, очереди строительства/исследований).  
  *Примечание:* доступ влияет только на **знание**, не на **контроль**.
- **Шанс слияния в день** (в состоянии Alliance):
  ```
  p_merge(day) = clamp( p0 + a * ln(1 + DaysInAlliance/7) + b * Stability - c * Strain, 0, p_max )
  ```
  Где: `p0=0.0015` (0.15%), `a≈0.002`, `b≈0.005`, `c≈0.003`, `p_max=0.12`.  
  `Stability` (0..1) растёт при совместных операциях и низких потерях; `Strain` — штраф за конфликты интересов/дефициты.
- **Инфляция стоимости исследований:**  
  Для i‑го завершённого шага (глобально или на ветку — опция баланса):
  ```
  Cost(i) = BaseCost * (1 + r)^i,   где r ∈ [0.10, 0.15]
  ```
- **Редкость после шага:** после завершения `Branch.Current` переопределяем следующий `Current`:
  ```
  pRare = clamp(pRareBase + α * QualityScore, 0, pRareMax)
  if (Roll(pRare)) pick Rare; else pick Common.
  // Anomalous возможна, если выполнены RequiresAssets ("ContainmentLab", "CaptureTeam") и Roll(pAnom),
  // где pAnom << pRare и также зависит от QualityScore и накопленной статистики образцов.
  ```
  *QualityScore* вычисляется как функция **QP/RP**: `QS = (ΣQP)/(ΣRP+ε)`, где RP — очки исследований/сутки, QP — “качество”.
- **Апгрейд зданий науки:**
  - **Количественный** (Tier+): RP↑ (напр. ×1.6), QP — ±0.  
  - **Качественный** (Spec+): QP↑ (напр. ×1.4), RP — ±0; **дороже** и **энергоёмче**.
  - ROI‑принцип: *одно улучшенное* выгоднее **двух базовых** на **10–30%** по целевому метрику категории.  
    Пример для Science: `RP(Tier1) = 1.0`, `RP(Tier2)=2.2` (на 10% лучше 2×1.0); `QP(Tier2)=1.4`.
- **Аномалии:** исследования требуют **образцы заражённых**; каждый шаг “сжигает” N образцов. Образцы добываются **командами поимки** и хранятся в **ContainmentLab**; утечки порождают риски (события).

### 1.3 Автоматизация
```csharp
public sealed class AutomationNetwork
{
    public int ComputeUnits;                 // суммарно от Server Farm
    public int FreeComputeUnits;
    public List<AutomationCore> Cores;
}

public sealed class AutomationCore
{
    public string Id;
    public int ConsumeCU;                    //  например, 10 CU
    public float PowerMW;                    //  большая энергозатрата
    public IAutomatable Target;              //  один объект: отряд ИЛИ здание
    public AutomationRecipe Recipe;          //  что именно автоматизируем
}

public interface IAutomatable { Guid InstanceId { get; } }
public enum RecipeKind { CaptureLoop, ResearchLoop, ProductionLoop, Convoy, Patrol }
```
- **Server Farm**: даёт **ComputeUnits (CU)** и требует энергию/обслуживание.  
- **Core**: берёт **1 цель** (отряд/здание), полностью ведёт процесс (например, цикл поимки: патруль→захват→доставка→пополнение).  
- При дефиците **энергии/CU** — ядро ставится на паузу, генерируется событие.  
- В off‑screen секторах рецепты работают **агрегировано** (без спавна юнитов).

---

## 2) Data (конфиги, JSON, SO)

### 2.1 Примеры JSON (упрощённо)
**States/Relations:**
```json
{
  "states": [
    { "id": "player", "title": "Союз Горного Края" },
    { "id": "red",    "title": "Красная Коммуна"   },
    { "id": "blue",   "title": "Северный Консорциум" }
  ],
  "relations": [
    { "a": "player", "b": "red",  "kind": "Hostile",  "stability": 0.2 },
    { "a": "player", "b": "blue", "kind": "None",     "stability": 0.0 }
  ]
}
```
**ResearchDefs:**
```json
{
  "research": [
    { "id":"eco.extraction.1", "branch":"economy.extraction", "rarity":"Common", "baseCostRP":100, "prereq":[] },
    { "id":"eco.extraction.R1","branch":"economy.extraction", "rarity":"Rare",   "baseCostRP":160, "prereq":["eco.extraction.1"]},
    { "id":"anom.capture.1",   "branch":"anomaly.capture",    "rarity":"Anomalous","baseCostRP":220,"requiresAssets":["ContainmentLab","CaptureTeam"]}
  ]
}
```
**Buildings (наука/контент/сервер/ядро):**
```json
{
  "buildings": [
    { "id":"Lab_T1", "type":"Science", "rp":1.0, "qp":0.1, "power":0.5 },
    { "id":"Lab_T2", "type":"Science", "rp":2.2, "qp":0.2, "power":0.8, "upgradeOf":"Lab_T1" },
    { "id":"Lab_Spec", "type":"Science", "rp":1.0, "qp":1.4, "power":1.2 },
    { "id":"ContainmentLab", "type":"Containment", "capacity":20, "power":1.5 },
    { "id":"ServerFarm_T1", "type":"Server", "computeUnits":20, "power":3.0 },
    { "id":"AutomationCore", "type":"Core", "consumeCU":10, "power":2.5 }
  ]
}
```

### 2.2 ScriptableObject каталоги
- `StateDef.asset`, `ResearchDef.asset`, `BuildingDef.asset`, `RecipeDef.asset`
- Версионирование: `SaveVersion++` и мигратор (старые сейвы → новые поля по умолчанию).

---

## 3) Application (циклы, события, сохранения)

### 3.1 EventBus — ключевые события
```
Diplomacy/RelationsChanged(stateA, stateB, kind)
Diplomacy/MergeHappened(newStateId, absorbedStateId)
Intel/AccessChanged(stateA, stateB, newAccess)
Research/StepCompleted(stateId, branchId, defId, rarity)
Research/NextStepAssigned(stateId, branchId, defId, rarity)
Anomaly/SamplesRequired(stateId, amount)
Anomaly/Breach(stateId, sectorId, severity)
Automation/CoreAttached(coreId, targetId)
Automation/CoreStalled(coreId, reason)
Power/GridOverload(stateId, deltaMW)
```

### 3.2 SimulationLoop
- Порядок: **Diplomacy→Intel→Research→Automation→Economy/Production→Combat/Anomaly→Events Flush**.  
- **Off‑screen**: Diplomacy/Research/Automation тикают **реже** для дальних секторов (агрегаты).

### 3.3 Сохранения
- Добавить разделы: `states[]`, `relations[]`, `researchProgress{}`, `automation{}`, `containment{}`.  
- Хранить `DaysInAlliance`, `Stability`, `QualityScore`, `ComputeUnits`, привязки ядер.  
- Сохранить **randomSeed** для бросков редкости/слияния.

---

## 4) AI (стратегия, тактика, дипломатия)

### 4.1 Решения дипломатии
- **Utility‑оценки**: выгода от Embassy/Alliance (торговля, совместный фронт, совпадение врагов).  
- **Стоимость**: риск слива информации, будущая вероятность слияния (может быть желанна/нежеланна).  
- **Политика**: агрессивные ИИ стремятся к войнам, прагматики — к посольствам на границах, коалиции — к союзам против общего врага.

### 4.2 Интел и FoW
- У каждого State своя **IntelLayer**; решения строятся на основании доступного intel.  
- При Embassy — AI рассматривает видимые юниты союзника в тактических оценках, но не планирует их использовать.

### 4.3 Слияние
- Если `Roll(p_merge)` — инициировать Merge: событие, переносятся владения/юниты/экономика; конфликты задач разрешаются приоритетами.  
- Новый AI выбирается по правилу (напр., “старший союзник” либо “наибольшая экономика”).

---

## 5) Presentation (UI/UX)

- **Экран старта**: выбор государства (иконка, описание перков).  
- **Дипломатия**: панель отношений (цвет/иконки None/Hostile/Embassy/Alliance), кнопки предложить/разорвать.  
- **Интел‑слои**: переключатели карты: “Наши”, “Посольства”, “Союзы”. Тултипы: что видно/скрыто.  
- **Слияние**: всплывающее событие (луп стинга SFX), лента изменений (перенос территорий/очередей).  
- **Исследования**: каждая ветка показывает **ровно один** доступный шаг и “неизвестные дальше”. Отсутствует точный шанс редких; можно показывать **косвенные намёки** (качество исследований “на уровне”).  
- **Аномалии**: индикаторы наличия образцов, риск утечки; панель автоматизации цикла.  
- **Автоматизация**: экран сети — **ServerFarm (CU)**, **Cores**, привязки, потребление энергии, состояния (Active/Paused/Stalled).

---

## 6) Баланс и константы (первичный сет)
- `p0=0.15%/day`, `p_max=12%/day`, `α=0.25`, `pRareBase=8%`, `pRareMax=40%`, `pAnomBase=1%` (строго реже).  
- Инфляция: `r_common=0.12`, `r_rare=0.14`, `r_anom=0.15` (умножается на BaseCost).  
- ROI здания (прирост к 2×базовых): Economy +10%, Military +15%, Science +30%, Containment +20%.  
- Сервер: `ServerFarm_T1 = 20 CU`; `Core` потребляет `10 CU`, `2.5 MW`.

---

## 7) План внедрения (4 коротких спринта)

### Спринт 1 — Государства и видимость (1–1.5 недели)
**Что делаем:** модели State/Relation/Intel, EventBus‑события, FoW на IntelLayer, стартовый экран выбора, UI дипломатии (минимум), Embassy/Alliance логика доступа.  
**Готово, когда:** AI не видит чужих без отношений; при Embassy видит юниты/постройки; при Alliance видит всё, но не управляет чужими; работает сохранение/загрузка.

### Спринт 2 — Слияние и экономика совместимости (1 неделя)
**Что делаем:** формула `p_merge`, таймеры, миграция владений, разрешение конфликтов очередей, UI события.  
**Готово, когда:** ежедневный ролл, стабильность влияет; слияние создаёт одно государство, один AI; сейвы валидны.

### Спринт 3 — Исследования v2 (1.5 недели)
**Что делаем:** ветки “один видимый шаг”, редкости, QualityScore, апгрейды Lab (RP/QP), инфляция, gating аномалий.  
**Готово, когда:** завершаешь шаг — назначается следующий; редкие иногда выпадают; без Containment/Capture аномалии недоступны; ROI зданий соблюдён.

### Спринт 4 — Аномалии и Автоматизация (1.5 недели)
**Что делаем:** ContainmentLab, CaptureTeam, расход образцов; ServerFarm (CU), AutomationCore (1 цель), рецепты (CaptureLoop/ResearchLoop); off‑screen агрегаты.  
**Готово, когда:** цикл “поимка→доставка→исследование” работает вручную и под ядром; при дефиците энергии/CU ядро в паузе; UI сети автоматизации.

---

## 8) Тест‑план и инварианты

- **Дипломатия/Интел:** без отношений — AI нулевое знание; Embassy — нет доступа к экономике/задачам; Alliance — полный доступ, контроль только своего.  
- **Слияние:** детерминированный сид, миграция владений корректна, поведение AI не ломается, сейв/лоад устойчив.  
- **Исследования:** стоимость монотонно растёт; выпадение редких коррелирует с QP; шанс скрыт в UI.  
- **ROI апгрейдов:** одно улучшенное ≥ (2 базовых) × (1.10..1.30) по метрике категории.  
- **Аномалии:** без Containment/Capture — заблокированы; образцы списываются; утечки вызывают события.  
- **Автоматизация:** ядро управляет ровно одной целью; пауза при нехватке CU/энергии; off‑screen даёт равный итог on‑screen при долгосрочной проверке (погрешность ≤5%).

---

## 9) Риски и меры
- **Сложность UI веток:** начнём с “одной карточки на ветку” + лог. лента.  
- **Баланс шансов:** телеметрия/дроп‑таблица; ограничим pRareMax и p_merge.  
- **Фризы при слиянии:** готовим батч‑миграцию (N объектов/кадр).  
- **Эксплойт редкости:** скрытый QS, но визуальные “намёки”; анти‑спам (кулдаун редких).  
- **Голод по образцам:** ранняя автоматизация CaptureLoop с лимитами дальности/риска.

---

## 10) Хуки интеграции (куда класть код)
```
/Game/Domain/States/*.cs          // State, Relation, IntelLayer
/Game/Domain/Research/*.cs        // ResearchProgress, Branch, rarity logic
/Game/Domain/Anomaly/*.cs         // Samples, Containment
/Game/Domain/Automation/*.cs      // Network, Core, IAutomatable
/Game/Application/Systems/*.cs    // DiplomacySystem, ResearchSystemV2, AutomationSystem
/Game/AI/Strategic/*.cs           // DiplomacyPlanner, MergeDecider
/Game/Presentation/UI/*.cs        // UI дипломатии, исслед., авто‑сети
/Game/Data/Defs/*.asset           // SO каталоги: State/Research/Building/Recipe
/Game/Infrastructure/Saving/*.cs  // Save vNext мигратор
```

---

### Приложение A — Псевдокод выбора следующего исследования
```csharp
void AssignNext(Branch b, State s) {
    var poolCommon = GetCandidates(b, ResearchRarity.Common, s);
    var poolRare   = GetCandidates(b, ResearchRarity.Rare, s);
    var poolAnom   = GetCandidates(b, ResearchRarity.Anomalous, s);

    float QS = s.Research.QualityScore; // скрытый показатель (ΣQP/ΣRP)
    float pRare = Mathf.Clamp(pRareBase + alpha * QS, 0, pRareMax);
    float pAnom = (HasAssets("ContainmentLab","CaptureTeam") ? baseAnom + beta * QS : 0);

    ResearchDef pick = null;
    if (Roll(pAnom) && poolAnom.Any()) pick = RandomOf(poolAnom);
    else if (Roll(pRare) && poolRare.Any()) pick = RandomOf(poolRare);
    else pick = RandomOf(poolCommon);

    b.Current = pick;
}
```

### Приложение B — События автоматизации (пример)
```
Automation/CoreAttached(core, target)
Automation/RecipeStarted(core, target, recipe)
Automation/RecipePaused(core, reason)
Automation/RecipeCompleted(core, target)
```

---

**Готово.** План совместим с текущей архитектурой, поддерживает off‑screen симуляцию и скрытую редкость исследований. Следующий шаг — согласовать баланс констант и начать Спринт 1 (States+Intel).