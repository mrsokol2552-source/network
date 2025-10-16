# Музыкальная система (Unity) — интеграция и правила

## 0) Назначение и жёсткий маппинг каталогов
В проекте используются **каталоги с двумя треками** в каждом:

- **A = Calm** (мирная/спокойная обстановка)  
- **B = Tense** (напряжение, тревога)  
- **C = MainMenu / WorldMap** (главный трек, карта мира) — **вне** машины состояний  
- **D = Stealth** (скрытность/инфильтрация)  
- **Aftermath / Ruins = Aftermath** (пост-бой/разгром)

> Внимание: **C не используется для боевых состояний**. Пока нет отдельных War‑треков, **War** играет треки из **B (Tense)**, но с «боевым слоем» через микшер (снапшот/параметр). Переходы между снапшотами выполняем через `AudioMixer.TransitionToSnapshots`.

---

## 1) Подготовка ассетов и импорт аудио
1. Исходники: **48 kHz / 24‑bit WAV**.  
2. В Unity для BGM используйте **Compressed (Vorbis)** и при необходимости **Load In Background** для фоновой подгрузки.  
3. Для длинных треков включайте подходящий **Load Type** (обычно *Streaming* для фоновой музыки).  
4. **Не** кладите музыку в `Resources/` — используем **Addressables** (управляемая загрузка/выгрузка, экономия памяти).

---

## 2) Addressables: метки и загрузка
1. Создайте группы Addressables:  
   `Music_A`, `Music_B`, `Music_C`, `Music_D`, `Music_Aftermath`, `Music_Ruins`.  
2. Всем клипам присвойте **лейблы** этих групп.  
3. В рантайме загружайте клипы **по лейблу**: `Addressables.LoadAssetsAsync<AudioClip>(label, ...)`.  
4. Храните и релизьте `AsyncOperationHandle` при выгрузке сцены, чтобы освобождать память.

---

## 3) AudioMixer: группы, снапшоты, параметры
- Создайте `MusicMixer` с группами (минимум): `Main`, `Drums`, `Bass`, `Strings`, `Lead`, `Atmos`, `FX` (для вертикальных слоёв).  
- Снапшоты: `Calm`, `Tense`, `War`, `Stealth`, `Aftermath`.  
- Переходы между снапшотами — через `AudioMixer.TransitionToSnapshots()` (0.25–0.40 c).  
- Экспонируйте параметры (например, `Music_Tension`, `Music_War`) для тонкой подмешки стемов.

---

## 4) Машина состояний (сектора) — кратко
- Приоритет: **Aftermath → War → Stealth → Tense → Calm**.  
- Пороги (пример): `War in 0.65 / out 0.55`, `Tense in 0.45 / out 0.35`, `Stealth in 0.60 / out 0.50`, `AftermathHold = 20s`, общий `Hold = 12s`.  
- **Жёсткие ограждения**:  
  - В состоянии **War** выбираются **только** клипы из `Music_B` (или `Music_War`, когда появится).  
  - **C (MainMenu/WorldMap)** не участвует в state‑machine.

---

## 5) Безщёлочные стыки и лупы
Используйте **DSP‑планирование**:

```csharp
double now = AudioSettings.dspTime; // точное время аудио‑системы
double start = now + 0.10;          // небольшой lead
nextSource.clip = nextClip;
nextSource.PlayScheduled(start);    // sample‑accurate старт
if (currentSource.isPlaying)
    currentSource.SetScheduledEndTime(start + 0.25); // мягкий кросс‑фейд
```

Подход с двумя `AudioSource` (A/B) обеспечивает точные стыки и отсутствие «щёлков».

---

## 6) Конфигурация (JSON)
Файл `Assets/Configs/MusicConfig.json`:

```json
{
  "labelMap": {
    "MainMenu": "Music_C",
    "Calm": "Music_A",
    "Tense": "Music_B",
    "War": "Music_B",              
    "Stealth": "Music_D",
    "Aftermath": ["Music_Aftermath", "Music_Ruins"]
  },
  "thresholds": {
    "warIn": 0.65, "warOut": 0.55,
    "tenseIn": 0.45, "tenseOut": 0.35,
    "stealthIn": 0.60, "stealthOut": 0.50,
    "holdSeconds": 12,
    "aftermathHold": 20
  },
  "fallback": {
    "War": "Tense",
    "Tense": "Calm",
    "Stealth": "Calm",
    "Aftermath": "Calm"
  },
  "rotation": "DeterministicHash"
}
```

> Когда появятся отдельные War‑треки, замените `"War": "Music_B"` на `"War": "Music_War"` — код менять не нужно.

---

## 7) Интеграция в сцену — чек‑лист
1. В сцене создайте объект `MusicDirector`, прикрепите **два** `AudioSource` (`A`, `B`), назначьте `MusicMixer` и снапшоты.  
2. Загрузите банки клипов по лейблам Addressables и выполните **preflight‑валидацию**: у каждого состояния ≥1 клип; если банк `War` пуст — мягкий фолбэк только в `Tense`.  
3. `MainMenu/WorldMap` играет **только** из `Music_C` и **вне** state‑machine.  
4. Переходы — через снапшоты; стыки и лупы — через `dspTime`/`PlayScheduled`/`SetScheduledEndTime`.  
5. Перед тестом — **Build Addressables**, иначе загрузка по лейблам не найдёт бандлы.

---

## 8) Мини‑паттерны (псевдокод)

**Детерминированный выбор клипа (A/B):**
```csharp
int idx = Mathf.Abs(Hash(sectorId) + cycleCounter) % clips.Count;
var clip = clips[idx];
```

**Переход снапшота:**
```csharp
mixer.TransitionToSnapshots(new[]{ snapTarget }, new[]{ 1f }, 0.35f);
```

---

## 9) QA‑чек‑лист
- [ ] **C ≠ боевые состояния**: банк `Music_C` не подключён в state‑machine.  
- [ ] В состоянии **War** используются только `Music_B` (или `Music_War` после добавления).  
- [ ] Загрузка идёт **по лейблам**, а не по путям.  
- [ ] Переходы между снапшотами плавные.  
- [ ] Стыки/лупы не «щёлкают» (везде `dspTime` + `PlayScheduled` + `SetScheduledEndTime`).  
- [ ] Импорт BGM: Vorbis, разумный Quality, при необходимости **Load In Background**.  
- [ ] Не используется `Resources/` для музыки; Addressables настроены и бандлы собираются.

---

## 10) Почему так
- **Addressables + labels** → масштабируемая загрузка наборов клипов и контроль памяти.  
- **AudioMixer + Snapshots** → плавная смена состояния/интенсивности.  
- **DSP‑планирование** → гарантированно точные, безщёлочные стыки и лупы.
