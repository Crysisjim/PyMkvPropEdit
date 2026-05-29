# ⚡ Installation

---

<details open>
<summary><b>🇫🇷 Français</b></summary>

## Méthode 1 — Version Portable (Recommandée)

> ✅ **La plus simple** — mkvpropedit et mkvmerge sont inclus dans le ZIP.

### Étape 1 — Télécharger

👉 [**Télécharger PyMkvPropEdit_v3.5_Portable_Full.zip**](https://github.com/Crysisjim/PyMkvPropEdit/releases/latest)

### Étape 2 — Extraire

Extraire le ZIP dans le dossier de votre choix :
```
C:\Tools\PyMkvPropEdit v3.5\
```

### Étape 3 — Installer Python

1. Télécharger [Python 3.10+](https://www.python.org/downloads/)
2. **⚠️ Cocher "Add Python to PATH"** lors de l'installation
3. Redémarrer si nécessaire

### Étape 4 — Lancer

Double-cliquer sur **`run.bat`**

Le launcher va automatiquement :
- ✅ Vérifier Python
- ✅ Installer Pillow, numpy, scipy, tkinterdnd2, win11toast
- ✅ Configurer les chemins vers mkvpropedit et mkvmerge (dossier `mkvtools/`)
- ✅ Lancer l'application

### Étape 5 (Optionnel) — FFmpeg

Pour les fonctionnalités **Audio Sync** et **Extraction de frames** :
1. Télécharger [FFmpeg](https://ffmpeg.org/download.html) (builds Windows par gyan.dev)
2. Extraire `ffmpeg.exe` et `ffprobe.exe` quelque part
3. Dans l'app : onglet **Options** → renseigner les chemins FFmpeg et FFprobe

---

## Méthode 2 — Depuis les sources (Développeurs)

```bash
git clone https://github.com/Crysisjim/PyMkvPropEdit.git
cd PyMkvPropEdit
pip install -r requirements.txt
pythonw "PyMkvPropEdit v3.5.pyw"
```

Puis dans l'onglet **Options** :
- Renseigner le chemin de `mkvpropedit.exe` (depuis MKVToolNix installé)
- Renseigner le chemin de `mkvmerge.exe`

</details>

---

<details>
<summary><b>🇬🇧 English</b></summary>

## Method 1 — Portable Version (Recommended)

> ✅ **Easiest** — mkvpropedit and mkvmerge are included in the ZIP.

### Step 1 — Download

👉 [**Download PyMkvPropEdit_v3.5_Portable_Full.zip**](https://github.com/Crysisjim/PyMkvPropEdit/releases/latest)

### Step 2 — Extract

Extract the ZIP wherever you like:
```
C:\Tools\PyMkvPropEdit v3.5\
```

### Step 3 — Install Python

1. Download [Python 3.10+](https://www.python.org/downloads/)
2. **⚠️ Check "Add Python to PATH"** during installation
3. Restart if needed

### Step 4 — Launch

Double-click **`run.bat`**

The launcher will automatically:
- ✅ Check Python
- ✅ Install Pillow, numpy, scipy, tkinterdnd2, win11toast
- ✅ Configure paths to mkvpropedit and mkvmerge (from `mkvtools/` folder)
- ✅ Launch the application

### Step 5 (Optional) — FFmpeg

For **Audio Sync** and **Frame Extraction** features:
1. Download [FFmpeg](https://ffmpeg.org/download.html) (gyan.dev Windows builds)
2. Extract `ffmpeg.exe` and `ffprobe.exe` somewhere
3. In the app: **Options** tab → set FFmpeg and FFprobe paths

---

## Method 2 — From Source (Developers)

```bash
git clone https://github.com/Crysisjim/PyMkvPropEdit.git
cd PyMkvPropEdit
pip install -r requirements.txt
pythonw "PyMkvPropEdit v3.5.pyw"
```

Then in the **Options** tab:
- Set the path to `mkvpropedit.exe` (from your MKVToolNix installation)
- Set the path to `mkvmerge.exe`

</details>
