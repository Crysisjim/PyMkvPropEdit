<div align="center">
  <img src="vivi.png" width="140"/>

# PyMkvPropEdit

![Version](https://img.shields.io/badge/version-3.7-blue?style=for-the-badge)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6?style=for-the-badge&logo=windows)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![MKVToolNix](https://img.shields.io/badge/MKVToolNix-bundled%20%2F%20system-orange?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)
[![Wiki](https://img.shields.io/badge/wiki-available-purple?style=for-the-badge)](https://github.com/Crysisjim/PyMkvPropEdit/wiki)

**Interface graphique batch pour `mkvpropedit` — héritière de JMkvpropedit**

*Batch GUI for `mkvpropedit` — successor to JMkvpropedit*

[📦 Télécharger / Download](https://github.com/Crysisjim/PyMkvPropEdit/releases/latest) &nbsp;•&nbsp; [📖 Wiki](https://github.com/Crysisjim/PyMkvPropEdit/wiki) &nbsp;•&nbsp; [🐛 Issues](https://github.com/Crysisjim/PyMkvPropEdit/issues)

</div>

---

## 🇫🇷 Description

PyMkvPropEdit est une **interface graphique avancée** pour [`mkvpropedit`](https://mkvtoolnix.download/) (inclus dans MKVToolNix). Elle permet de modifier en **batch** les propriétés des fichiers `.mkv` : pistes, langues, noms, jaquettes, chapitres, et bien plus.

> Inspirée par JMkvpropedit, entièrement réécrite en Python avec de nombreuses fonctionnalités additionnelles.

## 🇬🇧 Description

PyMkvPropEdit is an advanced **GUI for [`mkvpropedit`](https://mkvtoolnix.download/)** (bundled with MKVToolNix). It enables **batch modification** of `.mkv` file properties: tracks, languages, names, cover art, chapters, and more.

> Inspired by JMkvpropedit, fully rewritten in Python with many additional features.

---

## 🚀 Installation

### 🇫🇷 Version EXE Portable (Recommandée)

> **Aucun Python requis** — `mkvpropedit`, `mkvmerge` et dépendances sont embarqués.

1. **[📦 Télécharger PyMkvPropEdit v3.7 EXE](https://github.com/Crysisjim/PyMkvPropEdit/releases/latest)**
2. Extraire le ZIP
3. Double-cliquer **`PyMkvPropEdit.exe`**
4. Au **premier lancement**, choisir entre MKVToolNix **intégré** (aucune installation requise) ou **système** (MKVToolNix déjà installé)

### 🇬🇧 EXE Portable Version (Recommended)

> **No Python required** — `mkvpropedit`, `mkvmerge` and all dependencies bundled.

1. **[📦 Download PyMkvPropEdit v3.7 EXE](https://github.com/Crysisjim/PyMkvPropEdit/releases/latest)**
2. Extract the ZIP
3. Double-click **`PyMkvPropEdit.exe`**
4. On **first launch**, choose between **bundled** MKVToolNix (no installation needed) or **system** MKVToolNix (already installed)

### 🇫🇷 Version Script (Développeurs)

```bash
git clone https://github.com/Crysisjim/PyMkvPropEdit.git
cd PyMkvPropEdit
pip install -r requirements.txt
pythonw "PyMkvPropEdit v3.7.pyw"
```

### 🇬🇧 Script Version (Developers)

```bash
git clone https://github.com/Crysisjim/PyMkvPropEdit.git
cd PyMkvPropEdit
pip install -r requirements.txt
pythonw "PyMkvPropEdit v3.7.pyw"
```

---

## ✨ Fonctionnalités / Features

| Onglet / Tab | 🇫🇷 | 🇬🇧 |
|-------------|-----|-----|
| 🚀 **Batch Pro** | Renommage auto TVDB/TMDB/TVmaze + métadonnées Kodi + réordonnancement pistes + sync | Auto-rename TVDB/TMDB/TVmaze + Kodi metadata + track reorder + sync |
| 🎬 **Video / Audio / Sous-titres** | Nom, langue, flags default/forced par piste | Name, language, default/forced flags per track |
| 📖 **Chapitres / Chapters** | Import XML, édition en ligne, suppression | XML import, inline editing, deletion |
| 🖼️ **Image de couverture / Cover** | Ajout/remplacement jaquette JPG/PNG | Add/replace JPG/PNG cover art |
| ⚙️ **Général / General** | Titre, numérotation, suppression tags | Title, custom numbering, tag deletion |
| 🎵 **Audio Sync** | Sync auto par corrélation FFT (numpy/scipy) | Auto sync via FFT cross-correlation |
| 🎵🎵 **Audio Sync Batch** | Idem sur dossier entier | Same, on entire folders |
| 🎥 **Frame Check** | Vérification frames original vs encodé | Frame/duration verification: original vs encoded |
| 🖼️ **Extraire / Extract Frames** | Extraction JPG/PNG/BMP avec qualité | JPG/PNG/BMP extraction with quality control |
| 📊 **MediaInfo** | Analyse complète pistes, chapitres | Full track, chapter, attachment analysis |
| 💾 **Préréglages / Presets** | Sauvegarde/chargement configurations | Save/load configurations |
| 🔧 **Options** | Chemins outils, thème, **langue EN/FR** | Tool paths, theme, **EN/FR language toggle** |

### 🇫🇷 Points forts &nbsp;&nbsp; / &nbsp;&nbsp; 🇬🇧 Highlights

- ✅ **Batch Pro** — renommage auto + métadonnées Kodi (TVDB/TMDB/TVmaze) &nbsp;/&nbsp; **Batch Pro** — auto-rename + Kodi metadata (TVDB/TMDB/TVmaze)
- ✅ **Traitement batch** — des dizaines de fichiers en une opération &nbsp;/&nbsp; **Batch processing** — dozens of files at once
- ✅ **Drag & Drop** — glisser-déposer les MKV &nbsp;/&nbsp; drag & drop MKV files
- ✅ **Interface bilingue EN/FR** — toggle dans Options &nbsp;/&nbsp; **Bilingual EN/FR UI** — switchable in Options
- ✅ **Notifications Windows 11** après chaque batch &nbsp;/&nbsp; **Windows 11 notifications** after each batch
- ✅ **EXE autosuffisant** — Python non requis &nbsp;/&nbsp; **Self-contained EXE** — no Python needed
- ✅ **Thème clair/sombre** &nbsp;/&nbsp; **Light/dark theme**
- ✅ **Export/Import paramètres JSON** &nbsp;/&nbsp; **JSON settings export/import**
- ✅ **UI thread-safe** — non bloquée pendant le traitement &nbsp;/&nbsp; non-blocking during processing

---

## 📦 Prérequis / Requirements

| Composant / Component | Requis / Required | Notes |
|----------------------|-------------------|-------|
| **Windows 10/11** | ✅ | — |
| **Python 3.10+** | ✅ Script only | Pas pour l'EXE / Not for EXE |
| **MKVToolNix** | ✅ Inclus / Bundled | Dans le ZIP / In the ZIP |
| **FFmpeg** | ⚠️ Recommandé | Audio Sync + Frame Extraction |
| **numpy / scipy** | ⚠️ Auto-installé | Audio Sync uniquement / only |
| **win11toast** | ⚠️ Auto-installé | Notifications Windows 11 |

---

## 🔑 Clés API (onglet Batch Pro) / API Keys (Batch Pro tab)

> 🇫🇷 Le renommage automatique et les métadonnées utilisent **TVDB**, **TMDB** et **TVmaze**.
> **TVmaze** fonctionne sans clé (séries uniquement). **TVDB** et **TMDB** nécessitent une clé API **gratuite**.
> Collez vos clés dans **Options** (champs masqués, sauvegardés localement).
>
> 🇬🇧 Auto-rename and metadata use **TVDB**, **TMDB** and **TVmaze**.
> **TVmaze** needs no key (series only). **TVDB** and **TMDB** require a **free** API key.
> Paste your keys in **Options** (masked fields, stored locally).

### 🎬 TheTVDB (recommandé pour Kodi / recommended for Kodi)

1. Créer un compte sur **[thetvdb.com](https://thetvdb.com/auth/register)**
2. Aller dans **[Dashboard → API Access](https://thetvdb.com/dashboard/account/apikey)**
3. Générer une clé **API v4** (project key)
4. Copier la clé dans **Options → Clé API TheTVDB**

### 🎥 TMDB (réalisateurs / producteurs / studios — directors / producers / studios)

1. Créer un compte sur **[themoviedb.org](https://www.themoviedb.org/signup)**
2. Aller dans **[Paramètres → API](https://www.themoviedb.org/settings/api)**
3. Demander une clé **API (v3 auth)** — usage personnel / gratuit
4. Copier la **API Key (v3 auth)** dans **Options → Clé API TMDB**

### 🆓 TVmaze

- Aucune clé requise / No key needed — fallback automatique pour les séries / automatic series fallback.

> 🔒 Les clés sont stockées uniquement dans votre `pymkvpropedit_settings.json` local, jamais transmises ailleurs.
> Keys are stored only in your local `pymkvpropedit_settings.json`, never sent anywhere else.

---

## 🗂️ Structure

```
PyMkvPropEdit/
├── PyMkvPropEdit v3.7.pyw   # Application principale / Main app
├── run.bat                  # Launcher (script version)
├── requirements.txt         # Python dependencies
├── vivi.png / vivi.ico      # App icon
├── backroom.jpg             # About background
├── success/failure/warning.jpg
└── mkvtools/                # Bundled in portable ZIP only
    ├── mkvpropedit.exe
    ├── mkvmerge.exe
    └── mkvextract.exe
```

---

## 🆕 Changelog

<details open>
<summary><b>v3.7 — Batch Pro: FileBot-like auto-rename + Kodi/MetaX-level metadata</b></summary>

**🇫🇷 Nouvel onglet Batch Pro 🚀**
- **[NEW]** Renommage automatique via **TVDB → TMDB → TVmaze** (combobox choix API + langue)
  - Séries : `Titre - S01E07 - Nom épisode.mkv` &nbsp;•&nbsp; Films : `Titre (2025) 1080p x265 Dolby Vision.mkv`
  - Résolution / codec / HDR détectés automatiquement (mkvmerge + ffprobe)
- **[NEW]** **Métadonnées Kodi/MetaX** : tags MKV (titre, show, description courte/longue, genres, acteurs, **réalisateur/scénariste/producteur/studio**, rating, IMDB, date) + NFO `kodi-metadata` embarqué + cover art téléchargé
- **[NEW]** **Picker visuel** multi-sources : choisir indépendamment illustration / description / synopsis / cast / crew / genres entre TVDB, TMDB et TVmaze (miniatures + dimensions, "appliquer à tous")
- **[NEW]** **Réordonnancement des pistes** par modèle (type + langue + forced), détection des fichiers hétérogènes
- **[NEW]** **Pipeline combiné** : sync audio + réordonnancement en 1 seul passage mkvmerge, puis mkvpropedit, métadonnées, renommage/déplacement
- **[NEW]** Dossier de sortie optionnel, barre de progression dédiée (%/ETA/temps écoulé/compteur N total)
- **[NEW]** Champs clés API TVDB + TMDB dans Options

**🇬🇧 New Batch Pro tab 🚀**
- **[NEW]** Auto-rename via **TVDB → TMDB → TVmaze** (API + language picker)
- **[NEW]** **Kodi/MetaX-level metadata**: MKV tags (title, show, short/long description, genres, actors, **director/writer/producer/studio**, rating, IMDB, date) + embedded `kodi-metadata` NFO + downloaded cover art
- **[NEW]** **Visual multi-source picker**: pick illustration / description / synopsis / cast / crew / genres independently across TVDB, TMDB, TVmaze
- **[NEW]** **Track reordering** by template (type + language + forced), heterogeneous-file detection
- **[NEW]** **Combined pipeline**: audio sync + reorder in a single mkvmerge pass, then mkvpropedit, metadata, rename/move
- **[NEW]** Optional output folder, dedicated progress bar (%/ETA/elapsed/N total counter)

</details>

<details>
<summary><b>v3.5 — Bilingual UI + Windows 11 Notifications + EXE Portable</b></summary>

- **[NEW]** Interface bilingue EN/FR — toggle dans Options / EN/FR bilingual UI
- **[NEW]** Notifications Windows 11 (win11toast) après batch, sync, extraction
- **[NEW]** EXE portable autosuffisant (PyInstaller) — aucun Python requis
- **[NEW]** mkvpropedit, mkvmerge, mkvextract inclus dans les deux ZIPs
- **[NEW]** run.bat auto-configure les chemins mkvtools au 1er lancement
- **[NEW]** ~70 clés de traduction — tous les onglets, boutons, labels

</details>

<details>
<summary><b>v3.4 — Corrections majeures</b></summary>

- Apostrophes préservées dans les noms de pistes (français)
- UI non bloquée pendant le traitement (thread background)
- ET.tostring corrigé pour Python 3.8+
- Nom couverture lu depuis le champ UI
- MediaInfo : chapitres affichés correctement
- calculate_delay : protection tableau vide
- NamedTemporaryFile correctement fermé sur Windows

</details>

<details>
<summary><b>v3.3 — Audio Sync amélioré</b></summary>

- Offset de début configurable (était hardcodé 300s)
- Auto-ajustement pour fichiers courts (OPs/EDs)
- Champ "Début analyse"

</details>

<details>
<summary><b>v3.2 — Frame Extractor</b></summary>

- Contrôle qualité JPG/PNG
- Extraction frame précise par timecode ou numéro
- Conversion frame → timecode via FPS

</details>

<details>
<summary><b>v3.1 — Support fichiers raw</b></summary>

- HEVC/H264/H265 raw (fallback durée)
- FFmpeg/FFprobe path configurables
- Drag & drop fallback gracieux

</details>

<details>
<summary><b>v3.0 — Refactoring majeur</b></summary>

- Thread safety via after(), AudioSyncMixin
- Logging, tempfile fix, APP_DIR
- Onglet MediaInfo, barre de statut
- Raccourcis clavier, export/import JSON

</details>

---

## 🤝 Contribuer / Contributing

1. Fork the project
2. `git checkout -b feature/my-feature`
3. Commit + Push
4. Open a Pull Request

---

## 📄 Licence / License

- **PyMkvPropEdit** — MIT — © 2026 Crysisjim
- **MKVToolNix** (bundled) — GPL v2 — © Moritz Bunkus
- **FFmpeg** (optional) — LGPL/GPL

---

<div align="center">

**Fait avec ❤️ par [Crysisjim](https://github.com/Crysisjim)**

*Companion tool for [MKVToolNix](https://mkvtoolnix.download/)*

</div>
