# 🎵 Audio Sync — Guide

---

<details open>
<summary><b>🇫🇷 Français</b></summary>

## Principe

L'onglet **Audio Sync** calcule automatiquement le décalage temporel entre deux pistes audio en utilisant une **corrélation croisée FFT** (via numpy/scipy).

> **Cas d'usage typique :** synchroniser le doublage français ou anglais sur la piste japonaise d'un épisode d'anime.

## Prérequis

- **numpy** et **scipy** installés (via `run.bat` ou `pip install numpy scipy`)
- **FFmpeg** configuré dans Options

## Utilisation — Single File (onglet Audio Sync 🎵)

### 1. Charger le fichier

Cliquer sur **"Ouvrir MKV"** et sélectionner le fichier `.mkv`.

Les pistes audio et sous-titres s'affichent dans le tableau.

### 2. Configurer

| Paramètre | Description |
|-----------|-------------|
| **Langue de référence** | Langue de la piste maître (ex: `jpn` pour japonais) |
| **Durée d'analyse** | Durée en secondes de l'extrait analysé (120s recommandé) |
| **Début analyse** | Position de départ en secondes (300s = 5min pour episodes standard, 0 pour OPs/EDs courts) |

### 3. Analyser

Cliquer sur **"Lancer l'Analyse Auto 🔍"**

Le processus :
1. Extrait la piste de référence via FFmpeg
2. Extrait chaque autre piste audio
3. Calcule la corrélation FFT → délai en millisecondes
4. Propage le délai aux sous-titres de même langue

### 4. Vérifier & Appliquer

- Vérifier les délais affichés dans la colonne **"Delay Trouvé"**
- Cocher/décocher l'application aux sous-titres selon besoin
- Cliquer **"Appliquer les Delays au fichier 💾"**

→ Un nouveau fichier `_SYNC.mkv` est créé (l'original est préservé)

## Utilisation — Batch (onglet Audio Sync Batch 🎵🎵)

1. Ajouter les fichiers MKV (bouton ou glisser-déposer)
2. Configurer les mêmes paramètres
3. Cliquer **"Lancer le Batch 🔍"**
4. Une notification Windows 11 s'affiche à la fin

> ⚠️ Le batch crée un `_SYNC.mkv` pour chaque fichier.

## Conseils

- Pour les **épisodes standard** (24min) : Début = 300s, Durée = 120s
- Pour les **courts** (OPs/EDs, 90s) : Début = 0, Durée = 60-80s
- Si l'analyse échoue, réduire la Durée ou mettre Début = 0

</details>

---

<details>
<summary><b>🇬🇧 English</b></summary>

## How it works

The **Audio Sync** tab automatically calculates the time offset between two audio tracks using **FFT cross-correlation** (via numpy/scipy).

> **Typical use case:** synchronize French or English dubbing to the Japanese audio track of an anime episode.

## Requirements

- **numpy** and **scipy** installed (via `run.bat` or `pip install numpy scipy`)
- **FFmpeg** configured in Options

## Usage — Single File (Audio Sync 🎵 tab)

### 1. Load the file

Click **"Open MKV"** and select the `.mkv` file.

Audio and subtitle tracks are displayed in the table.

### 2. Configure

| Parameter | Description |
|-----------|-------------|
| **Reference language** | Master track language (e.g., `jpn` for Japanese) |
| **Analysis duration** | Duration in seconds of the analyzed excerpt (120s recommended) |
| **Analysis start** | Start position in seconds (300s = 5min for standard episodes, 0 for short OPs/EDs) |

### 3. Analyze

Click **"Start Auto Analysis 🔍"**

The process:
1. Extracts the reference track via FFmpeg
2. Extracts each other audio track
3. Computes FFT correlation → delay in milliseconds
4. Propagates the delay to subtitles of the same language

### 4. Review & Apply

- Check the delays shown in the **"Delay Found"** column
- Check/uncheck subtitle application as needed
- Click **"Apply Delays to File 💾"**

→ A new `_SYNC.mkv` file is created (original is preserved)

## Batch Usage (Audio Sync Batch 🎵🎵 tab)

1. Add MKV files (button or drag & drop)
2. Configure the same parameters
3. Click **"Start Batch 🔍"**
4. A Windows 11 notification appears when complete

> ⚠️ Batch creates a `_SYNC.mkv` file for each input.

## Tips

- For **standard episodes** (24min): Start = 300s, Duration = 120s
- For **short files** (OPs/EDs, 90s): Start = 0, Duration = 60-80s
- If analysis fails, reduce Duration or set Start = 0

</details>
