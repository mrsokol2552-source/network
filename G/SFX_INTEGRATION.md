# SFX_INTEGRATION.md — Интеграция звуковых эффектов в проект (Unity)

> Версия: 1.0 • Автор: Audio/Tech • Совместимо с `MUSIC_INTEGRATION.md`  
> Цель: стандартизировать **создание, импорт, маршрутизацию, воспроизведение и оптимизацию** SFX в нашей RTS.

---

## 0) Кратко: TL;DR чек‑лист
- Формат мастеров: **48 kHz / 24‑bit WAV**, **true peak ≤ −1 dBTP**.  
- Генерация длин: **по умолчанию 3 с**, UI one‑shot — 1 с, амбиенты — 6–10 с (склейка из 3‑с).  
- Громкость (ориентир): UI −18…−16 LUFS; in‑game SFX −16…−12 LUFS (короткие пики ок).  
- На экспорт в игру: OGG/PCM; **моно** там, где можно (foley/steps), **стерео** — для широких (взрывы/UI wide).  
- Нейминг: `SFX_<Категория>_<Событие>_<Var##>.wav`.  
- Вариативность: **5–8 вариантов** на событие; в коде: random pitch ±3–5%, volume ±1.5 dB.  
- Mixer‑группы: **SFX_UI, SFX_World, SFX_Combat, SFX_Voice, SFX_Ambience**. Экспонируем `SFX_Tension`, `SFX_War`, `OcclusionLPF`.  
- Импорт: one‑shot — **Decompress on Load**, лупы длинные — **Streaming**, средние — **Compressed In Memory**.  
- Пространство: 2D для UI, 3D для мира; кастомные **Rolloff** и **LPF** по расстоянию/укрытию.  
- Off‑screen/LOD: уменьшать громкость/полосу (LPF), сворачивать лупы толпы в дальних секторах.

---

## 1) Структура папок и нейминг
```
Assets/Audio/
  Mixers/             # .mixer и снапшоты (Calm/Tense/War)
  SFX/
    UI/               # клики, подтверждения, алерты
    World/            # двери, механика, окружение, толпы
    Combat/           # оружие, взрывы, попадания
    Voice/            # радио PTT, бипы, System VO
    Ambience/         # day/night, shortwave, ландшафты
  Addressables/
    Labels: SFX_UI, SFX_World, SFX_Combat, SFX_Voice, SFX_Ambience
```

**Имена файлов:**  
`SFX_<Категория>_<Событие>_<Var##>.wav` → `SFX_UI_Click_V03.wav`, `SFX_Combat_Explosion_M_V02.wav`

**Метаданные (CSV/JSON для каталога, опционально):**
```json
[
  {
    "id": "ui_click",
    "path": "Assets/Audio/SFX/UI/SFX_UI_Click_V01.wav",
    "group": "SFX_UI",
    "variants": 8,
    "length_ms": 120
  }
]
```

---

## 2) Спека контента
- **Мастера:** 48 kHz / 24‑bit WAV, true peak ≤ −1 dBTP.  
- **Громкость:** UI −18…−16 LUFS (короткий интеграл), боевые/мир — −16…−12 LUFS.  
- **Длины генерации:**  
  - UI one‑shot: генерируй ~1 с → резать до **80–300 мс** (fade 5–10 мс).  
  - Whoosh/alerts: генерируй 2–3 с → **180–600 мс**.  
  - Удары/двери: генерируй 2–3 с → **300–800 мс**.  
  - Выстрел/взрыв: генерируй 3 с (саб‑хвост) → **0.3–1.2 с**.  
  - Лупы (шаги, стройка, двигатель): генерируй 3 с → **1.2–1.8 с** seamless loop.  
  - Толпа/shortwave: генерируй 3 с × 2–4 → склей **6–10 с** луп.
- **Вариативность:** минимум **5–8** на событие (Var01..Var08).

---

## 3) Импорт в Unity (AudioImporter)
Для партий через Project Settings или ScriptedImporter (пример ниже).

**One‑shots (UI/мелкие):**
- Load Type: **Decompress on Load**
- Compression: **PCM** или Vorbis Q≈0.7 (если много)
- Force To Mono: **On** (кроме явно стерео)
- Preload Audio Data: **On**

**Средние лупы (шаги/стройка/двигатели):**
- Load Type: **Compressed In Memory**
- Compression: **Vorbis Q≈0.6–0.7**
- Force To Mono: On (если ок по восприятию)
- Loop: **On**, Fade‑in/out 5–10 ms в исходнике

**Длинные амбиенты:**
- Load Type: **Streaming**
- Compression: **Vorbis Q≈0.6**
- Stereo: **On**, Loop: **On**

**Пример пакетной настройки (Editor script, C#):**
```csharp
#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

public static class SfxImportPreset
{
    [MenuItem("Audio/Apply SFX Preset Selected")]
    public static void Apply()
    {
        foreach (var guid in Selection.assetGUIDs)
        {
            var path = AssetDatabase.GUIDToAssetPath(guid);
            var importer = AssetImporter.GetAtPath(path) as AudioImporter;
            if (importer == null) continue;

            var isAmbience = path.Contains("/Ambience/");
            var isUI = path.Contains("/UI/");

            var settings = importer.defaultSampleSettings;
            settings.sampleRateSetting = AudioSampleRateSetting.PreserveSampleRate;
            settings.loadType = isAmbience ? AudioClipLoadType.Streaming :
                                (isUI ? AudioClipLoadType.DecompressOnLoad : AudioClipLoadType.CompressedInMemory);
            settings.compressionFormat = isUI ? AudioCompressionFormat.PCM : AudioCompressionFormat.Vorbis;
            settings.quality = isUI ? 1.0f : 0.7f;

            importer.forceToMono = !path.Contains("/Combat/") && !isAmbience && !path.Contains("_ST_");
            importer.defaultSampleSettings = settings;
            importer.preloadAudioData = !isAmbience;

            importer.SaveAndReimport();
        }
    }
}
#endif
```

---

## 4) AudioMixer и маршрутизация
Группы (см. `MUSIC_INTEGRATION.md`):  
- **SFX_UI**, **SFX_World**, **SFX_Combat**, **SFX_Voice**, **SFX_Ambience** → все в `SFX/Main`, далее в `Master`.
- Экспонированные параметры:  
  - `SFX_Tension (0..1)` — добавка яркости (эквалайзер/Transient Shaper) на шинах.  
  - `SFX_War (0..1)` — поднимает боевые на +1..+2 dB, ослабляет музыку.  
  - `OcclusionLPF (0..1)` — глобальный LPF для укрытий/офф‑скрина.
- **Ducking:** В Calm/Tense музыка duck’ится SFX (side‑chain на Music). В War — duck меньше или отключён.

Снапшоты: **Calm / Tense / War** (времена кросс‑фейда 250–400 мс).

---

## 5) События → Звук (схема интеграции)
Все игровые события публикуются в EventBus (или аналог), `SfxManager` подписывается и мапит на клипы.

Примеры маппинга (сокр.):
```
OnUiClick                → SFX_UI_Click_* (rand)
OnResearchStarted        → SFX_UI_ResearchStart_*
OnResearchCompleted      → SFX_UI_ResearchDone_*
OnConvoyDepart/Arrive    → SFX_World_ConvoyDepart/Arrive_*
OnBuildPlaced/Started    → SFX_World_BuildPlace / SFX_World_BuildLoop (loop start)
OnBuildCompleted         → SFX_World_BuildDone_*
OnFootstep(unit, mat)    → SFX_World_Footstep_{Light|Heavy}_{mat}_*
OnFire(weapon)           → SFX_Combat_{RifleBurst|Cannon}_*
OnHit(surface)           → SFX_Combat_Impact_{Dirt|Concrete}_*
OnExplosionSmall/Medium  → SFX_Combat_Explosion_{S|M}_*
OnInfectionTick          → SFX_World_InfectionPulse_*
OnOutbreak               → SFX_World_InfectionSurge_*
OnRadioPtt(in/out)       → SFX_Voice_RadioPTT_{In|Out}_*
```

---

## 6) SfxManager (пример API)
```csharp
using UnityEngine;
using UnityEngine.Audio;
using System.Collections.Generic;

public class SfxManager : MonoBehaviour
{
    public static SfxManager I;
    [Header("Routing")]
    public AudioMixer mixer;
    public AudioMixerGroup sfxUI, sfxWorld, sfxCombat, sfxVoice, sfxAmbience;

    [Header("Banks")]
    public List<AudioClip> uiClick;
    public List<AudioClip> buildDone;
    public List<AudioClip> rifleBurst;
    // ... остальное

    [Range(0f, 0.05f)] public float randPitch = 0.03f;
    [Range(0f, 1.5f)] public float randVolDb = 1.0f;

    void Awake(){ I = this; }

    public void PlayUI(AudioClip clip)
    {
        var src = GetOneShotSource(sfxUI);
        SetupRandom(src);
        src.PlayOneShot(clip);
    }

    public void PlayWorldAt(AudioClip clip, Vector3 pos)
    {
        var src = GetOneShot3DSource(sfxWorld, pos);
        SetupRandom(src);
        src.PlayOneShot(clip);
    }

    public AudioSource PlayLoopAt(AudioClip clip, Vector3 pos, AudioMixerGroup grp)
    {
        var src = GetPooledSource();
        src.outputAudioMixerGroup = grp;
        src.transform.position = pos;
        src.loop = true;
        src.spatialBlend = grp == sfxUI ? 0f : 1f;
        src.clip = clip;
        src.Play();
        return src;
    }

    public void StopLoop(AudioSource src)
    {
        if (!src) return;
        src.Stop();
        ReturnToPool(src);
    }

    // --- helpers (pool/random) ---
    Queue<AudioSource> pool = new();
    AudioSource GetPooledSource()
    {
        if (pool.Count > 0) return pool.Dequeue();
        var go = new GameObject("SFX_AudioSource");
        go.transform.parent = transform;
        var src = go.AddComponent<AudioSource>();
        src.rolloffMode = AudioRolloffMode.Custom; // используем кривые проекта
        return src;
    }
    void ReturnToPool(AudioSource s){ s.clip=null; s.loop=false; pool.Enqueue(s); }

    AudioSource GetOneShotSource(AudioMixerGroup grp)
    {
        var s = GetPooledSource();
        s.outputAudioMixerGroup = grp;
        s.spatialBlend = 0f;
        return s;
    }
    AudioSource GetOneShot3DSource(AudioMixerGroup grp, Vector3 pos)
    {
        var s = GetPooledSource();
        s.outputAudioMixerGroup = grp;
        s.transform.position = pos;
        s.spatialBlend = 1f;
        return s;
    }
    void SetupRandom(AudioSource s)
    {
        s.pitch = 1f + Random.Range(-randPitch, randPitch);
        float volDb = Random.Range(-randVolDb, randVolDb);
        s.volume = Mathf.Pow(10f, volDb/20f);
    }
}
```

---

## 7) Пространство, затухание, окклюзия
- **UI:** `spatialBlend = 0`.  
- **Мир:** `spatialBlend = 1`, **Custom Rolloff** (кривая проекта); **MinDistance** подбираем так, чтобы ближний звук не был слишком громок.  
- **LPF/окклюзия:** параметр `OcclusionLPF (0..1)` в Mixer — повышается, если между источником и слушателем есть укрытие/стена или источник **off‑screen**.  
- **Off‑screen & LOD:** при сворачивании сектора → останавливаем дорогостоящие лупы, оставляем только агрегированные (толпа, shortwave) на низком уровне и с LPF.

---

## 8) Addressables и память
- Метки: **SFX_UI, SFX_World, SFX_Combat, SFX_Voice, SFX_Ambience**.  
- **One‑shots частые** — держим в памяти; **длинные амбиенты** — Streaming.  
- При смене сцены/сектора — выгружаем неиспользуемые группы (release by label).

---

## 9) Гайд по категориям (минимальный набор)
- **UI:** Click/Hover/Select/Confirm/Error/Panel Open/Close/Map Ping/Alert.  
- **Экономика/Логистика:** Research Start/Complete, Convoy Depart/Arrive, Path Blocked.  
- **Стройка/Фортификации:** Place (ghost), Build Start (loop), Build Complete, Trench Dig (loop).  
- **Юниты/Движение:** Footsteps (light/heavy; материалы), Vehicle Idle/Move (loops).  
- **Бой:** Rifle Burst, Heavy Cannon, Impact Dirt/Concrete, Explosion S/M, Bullet Whiz/Ricochet.  
- **Инфекция:** Infection Tick, Surge/Outbreak, Quarantine Placed/Breached.  
- **Мирные:** Crowd Safe/Panic (loops), Shelter Gate.  
- **Амбиент:** City Day/Night, Shortwave (loop).  
- **Радио:** PTT In/Out, Comms Beep.

---

## 10) Тесты и калибровка
- **Уровни:** прогнать контрольную сцену, выровнять относительные громкости (UI не перекрикивает бой; бой не давит музыку).  
- **Loop‑seamless:** бесшовность всех лупов (кросс‑фейд 5–10 мс + точка петли).  
- **Вариативность:** нет “machine‑gun effect” у повторяемых клипов.  
- **Ducking/Снапшоты:** проверить переходы Calm↔Tense↔War без щелчков.  
- **OC/LPF:** проверить поведение за стенами/офф‑скрином.  
- **Нагрузочные:** массовая стрельба + толпа + стройка — без треска/клиппинга; CPU/GC стабилен.

---

## 11) План интеграции (по шагам)
1. Создать группы в **AudioMixer**, экспонировать `SFX_Tension`, `SFX_War`, `OcclusionLPF`.  
2. Импортировать минимальный набор клипов (см. §9), применить пресет импортёра (§3).  
3. Разложить по Addressables (labels).  
4. Добавить `SfxManager` в сцену, связать MixerGroup’ы и банки клипов.  
5. Подписать `SfxManager` на EventBus (UI, Combat, World, Infection).  
6. Настроить **снапшоты** Mixer и автоматизацию параметров от гейм‑состояния.  
7. Прогнать чек‑листы (§10), зафиксировать уровни и кривые.  
8. Задокументировать пути и идентификаторы в аудио‑каталоге (CSV/JSON).

---

## 12) Приложение: пресеты генерации для @SoundEffect
- UI Click/Hover: `short UI blip, 120ms, bandpassed 800–3kHz, slight radio grit, no reverb`  
- Confirm/Success: `two-note chime, C–Eb, 250ms, subtle shimmer`  
- Error: `ui error tone, descending minor second, 200ms, soft distortion`  
- Panel Whoosh: `ui whoosh short, 180–220ms, air-noise, no low end`  
- Research Start/Done: `subtle spark + relay 250ms` / `warm chime triad 400ms`  
- Build Loop: `construction loop, light hammering 1.5s, band 200–4kHz`  
- Rifle Burst: `tactical rifle 3-round, dry, tight 180ms`  
- Explosion S/M: `explosion small 350ms tight` / `explosion medium 600ms controlled tail`  
- Crowd Safe/Panic: `crowd ambience loop 1.5s low band` / `crowd panic loop 1.5s lowpassed`  
- Shortwave: `shortwave static loop 1.5s gentle`

---

**Готово.** Этот документ — «живой»: по мере внедрения фиксируем уровни, кривые, карты событий и адреса. Совместим с музыкальными снапшотами из `MUSIC_INTEGRATION.md`.
