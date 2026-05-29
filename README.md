# 🎬 PyMkvPropEdit

<div align="center">

![Version](https://img.shields.io/badge/version-3.5-blue?style=for-the-badge)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6?style=for-the-badge&logo=windows)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![MKVToolNix](https://img.shields.io/badge/requires-MKVToolNix-orange?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)
![Wiki](https://img.shields.io/badge/wiki-available-purple?style=for-the-badge)

**Interface graphique batch pour `mkvpropedit` — héritière de JMkvpropedit**

*Batch GUI for `mkvpropedit` — successor to JMkvpropedit*

[📦 Télécharger / Download](https://github.com/Crysisjim/PyMkvPropEdit/releases/latest) • [📖 Wiki](https://github.com/Crysisjim/PyMkvPropEdit/wiki) • [🐛 Issues](https://github.com/Crysisjim/PyMkvPropEdit/issues)

</div>

---

<details open>
<summary><b>🇫🇷 Français</b></summary>

## Description

PyMkvPropEdit est une **interface graphique avancée** pour [`mkvpropedit`](https://mkvtoolnix.download/) (inclus dans MKVToolNix). Elle permet de modifier en **batch** les propriétés des fichiers `.mkv` : pistes, langues, noms, jaquettes, chapitres, et bien plus.

> Inspirée par JMkvpropedit, entièrement réécrite en Python avec de nombreuses fonctionnalités additionnelles.

## 🚀 Installation Portable (Recommandé)

> **Aucune configuration requise** — `mkvpropedit` et `mkvmerge` sont inclus dans le ZIP.

1. **[📦 Télécharger la dernière release](https://github.com/Crysisjim/PyMkvPropEdit/releases/latest)**
2. Extraire le ZIP
3. Installer **[Python 3.10+](https://www.python.org/)** *(cocher "Add Python to PATH")*
4. *(Optionnel)* Installer **[FFmpeg](https://ffmpeg.org/)** pour Audio Sync
5. Double-cliquer sur **`run.bat`**

## ✨ Fonctionnalités

| Onglet | Fonctionnalités |
|--------|----------------|
| 🎬 **Video / Audio / Sous-titres** | Nom, langue, flags default/forced par piste |
| 📖 **Chapitres** | Import XML, édition en ligne, suppression |
| 🖼️ **Image de couverture** | Ajout/remplacement jaquette JPG/PNG |
| ⚙️ **Général** | Titre, numérotation personnalisée, suppression tags |
| 🎵 **Audio Sync** | Synchronisation automatique par corrélation FFT |
| 🎵🎵 **Audio Sync Batch** | Idem sur dossier entier |
| 🎥 **Frame Check** | Vérification frames/durée original vs encodé |
| 🖼️ **Extraire Images** | Extraction frames JPG/PNG/BMP, contrôle qualité |
| 📊 **MediaInfo** | Analyse complète pistes, chapitres, pièces jointes |
| 💾 **Préréglages** | Sauvegarde/chargement configurations |
| 🔧 **Options** | Chemins outils, thème clair/sombre, **langue EN/FR** |

### Points forts
- ✅ **Traitement batch** — des dizaines de fichiers en une opération
- ✅ **Drag & Drop** — glisser-déposer les MKV directement
- ✅ **Bilingual EN/FR** — langue switchable dans Options
- ✅ **Notifications Windows 11** — toast après chaque batch
- ✅ **Thème clair/sombre**
- ✅ **Export/Import paramètres JSON**
- ✅ **Audio Sync FFT** (numpy/scipy)
- ✅ **UI thread-safe** — non bloquée pendant le traitement
- ✅ **Logging** complet dans `pymkvpropedit.log`

## 📦 Prérequis

| Composant | Requis | Notes |
|-----------|--------|-------|
| **Windows 10/11** | ✅ | — |
| **Python 3.10+** | ✅ | Cocher "Add to PATH" |
| **MKVToolNix** | ✅ Inclus ZIP | Fourni dans le bundle portable |
| **FFmpeg** | ⚠️ Recommandé | Audio Sync + Frame Extraction |
| **numpy / scipy** | ⚠️ Auto-installé | Audio Sync |
| **win11toast** | ⚠️ Auto-installé | Notifications Windows 11 |

</details>

---

<details>
<summary><b>🇬🇧 English</b></summary>

## Description

PyMkvPropEdit is an advanced **GUI for [`mkvpropedit`](https://mkvtoolnix.download/)** (bundled with MKVToolNix). It enables **batch modification** of `.mkv` file properties: tracks, languages, names, cover art, chapters, and more.

> Inspired by JMkvpropedit, fully rewritten in Python with many additional features.

## 🚀 Portable Install (Recommended)

> **Zero configuration** — `mkvpropedit` and `mkvmerge` are included in the ZIP.

1. **[📦 Download latest release](https://github.com/Crysisjim/PyMkvPropEdit/releases/latest)**
2. Extract the ZIP
3. Install **[Python 3.10+](https://www.python.org/)** *(check "Add Python to PATH")*
4. *(Optional)* Install **[FFmpeg](https://ffmpeg.org/)** for Audio Sync
5. Double-click **`run.bat`**

## ✨ Features

| Tab | Features |
|-----|----------|
| 🎬 **Video / Audio / Subtitles** | Name, language, default/forced flags per track |
| 📖 **Chapters** | XML import, inline editing, deletion |
| 🖼️ **Cover Image** | Add/replace JPG/PNG cover art |
| ⚙️ **General** | Title, custom numbering, tag deletion |
| 🎵 **Audio Sync** | Automatic sync via FFT cross-correlation |
| 🎵🎵 **Audio Sync Batch** | Same, on entire folders |
| 🎥 **Frame Check** | Frame/duration verification: original vs encoded |
| 🖼️ **Extract Frames** | JPG/PNG/BMP frame extraction with quality control |
| 📊 **MediaInfo** | Full track, chapter, attachment analysis |
| 💾 **Presets** | Save/load configurations |
| 🔧 **Options** | Tool paths, light/dark theme, **EN/FR language toggle** |

### Highlights
- ✅ **Batch processing** — dozens of files in one operation
- ✅ **Drag & Drop** — drop MKV files directly
- ✅ **Bilingual EN/FR** — switchable in Options tab
- ✅ **Windows 11 notifications** — toast after each batch
- ✅ **Light/dark theme**
- ✅ **JSON settings export/import**
- ✅ **FFT Audio Sync** (numpy/scipy)
- ✅ **Thread-safe UI** — responsive during processing
- ✅ **Full logging** to `pymkvpropedit.log`

## 📦 Requirements

| Component | Required | Notes |
|-----------|----------|-------|
| **Windows 10/11** | ✅ | — |
| **Python 3.10+** | ✅ | Check "Add to PATH" |
| **MKVToolNix** | ✅ Bundled | Included in portable ZIP |
| **FFmpeg** | ⚠️ Recommended | Audio Sync + Frame Extraction |
| **numpy / scipy** | ⚠️ Auto-installed | Audio Sync |
| **win11toast** | ⚠️ Auto-installed | Windows 11 Notifications |

</details>

---

## 🗂️ Structure du projet / Project structure

```
PyMkvPropEdit/
├── PyMkvPropEdit v3.5.pyw   # Application principale / Main app
├── run.bat                  # Launcher portable
├── requirements.txt         # Python dependencies
├── vivi.ico                 # App icon
├── backroom.jpg             # About tab background
├── success.jpg / failure.jpg / warning.jpg
└── mkvtools/                # Bundled MKVToolNix executables (portable ZIP only)
    ├── mkvpropedit.exe
    ├── mkvmerge.exe
    └── mkvextract.exe
```

---

## 🆕 Changelog

<details open>
<summary><b>v3.5 — Bilingual UI + Windows 11 Notifications</b></summary>

- **[NEW]** Bilingual EN/FR UI — language toggle in Options (restart to apply)
- **[NEW]** Windows 11 toast notifications after batch, audio sync, frame extraction
- **[NEW]** win11toast integration (auto-installed via requirements.txt)
- **[NEW]** Portable ZIP now bundles mkvpropedit, mkvmerge, mkvextract
- **[NEW]** run.bat auto-configures mkvtools paths on first launch

</details>

<details>
<summary><b>v3.4 — Bug fixes</b></summary>

- [FIX] sanitize_input: apostrophes preserved (French track names)
- [FIX] process_files: background thread (non-blocking UI)
- [FIX] ET.tostring encoding fixed for Python 3.8+
- [FIX] Cover attachment name reads from UI field
- [FIX] MediaInfo: chapters now display correctly
- [FIX] calculate_delay: guard against empty arrays
- [FIX] NamedTemporaryFile properly closed on Windows

</details>

<details>
<summary><b>v3.3 — Audio Sync improvements</b></summary>

- [FIX] Configurable analysis start offset (was hardcoded 300s)
- [FIX] Auto-adjust for files shorter than expected
- [NEW] "Début analyse" field for short files (OPs/EDs)

</details>

<details>
<summary><b>v3.2 — Frame Extractor</b></summary>

- [NEW] JPG quality control (q:v 1-31) and PNG compression (0-9)
- [NEW] Single precise frame extraction by timecode or frame number
- [NEW] Frame number → timecode via detected FPS

</details>

<details>
<summary><b>v3.1 — Raw file support</b></summary>

- [FIX] HEVC/H264/H265 raw file support (multi-fallback duration)
- [FIX] FFmpeg/FFprobe now use configured paths
- [FIX] tkdnd crash graceful fallback
- [NEW] FFmpeg & FFprobe path settings with auto-detection
- [NEW] Extended video: .hevc .h265 .264 .h264 .ivf .webm .ts

</details>

<details>
<summary><b>v3.0 — Major refactor</b></summary>

- [FIX] Thread safety: all GUI updates via after()
- [FIX] Proper exception handling + logging
- [FIX] tempfile.mktemp replaced
- [REFACTOR] run_hidden() helper, AudioSyncMixin
- [NEW] MediaInfo tab, status bar, keyboard shortcuts
- [NEW] JSON settings export/import, file logging

</details>

---

## 🤝 Contribuer / Contributing

1. Fork the project
2. Create your branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Open a Pull Request

---

## 📄 Licence / License

- **PyMkvPropEdit** — MIT License — © 2026 Crysisjim
- **MKVToolNix** (bundled) — GPL v2 — © Moritz Bunkus
- **FFmpeg** (optional) — LGPL/GPL — © FFmpeg team

---

<div align="center">

**Fait avec ❤️ par [Crysisjim](https://github.com/Crysisjim)**

*Companion tool for [MKVToolNix](https://mkvtoolnix.download/) — the best MKV toolkit.*

</div>
