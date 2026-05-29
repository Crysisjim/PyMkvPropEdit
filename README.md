# 🎬 PyMkvPropEdit

<div align="center">

![Version](https://img.shields.io/badge/version-3.4-blue?style=for-the-badge)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6?style=for-the-badge&logo=windows)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![MKVToolNix](https://img.shields.io/badge/requires-MKVToolNix-orange?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)

**Interface graphique batch pour `mkvpropedit` — héritière de JMkvpropedit**

*Batch GUI for `mkvpropedit` — successor to JMkvpropedit*

</div>

---

## 🆕 Nouveautés v3.4

- **[FIX]** `sanitize_input` : les apostrophes sont préservées (noms de pistes français corrects)
- **[FIX]** `process_files` : ne bloque plus le thread principal — UI responsive pendant le traitement
- **[FIX]** `_apply_chapter_names` : `ET.tostring` corrigé pour Python 3.8+ (`ValueError`)
- **[FIX]** Cover name : le champ "Nom de la pièce jointe" est désormais utilisé (au lieu de `cover.jpg` en dur)
- **[FIX]** MediaInfo Tab : les chapitres s'affichent maintenant correctement
- **[FIX]** Audio Sync : protection contre tableau vide dans `calculate_delay`
- **[FIX]** Gestion des fichiers temporaires (`NamedTemporaryFile`) robustifiée

## 📋 Description

PyMkvPropEdit est une **interface graphique avancée** pour [`mkvpropedit`](https://mkvtoolnix.download/) (inclus dans MKVToolNix). Elle permet de modifier en **batch** les propriétés des fichiers `.mkv` : pistes, langues, noms, jaquettes, chapitres, et bien plus.

> Inspirée par JMkvpropedit, entièrement réécrite en Python avec de nombreuses fonctionnalités additionnelles.

---

## ✨ Fonctionnalités

| Onglet | Fonctionnalités |
|--------|----------------|
| 🎬 **Video / Audio / Subtitle** | Nom, langue, flags default/forced par piste |
| 📖 **Chapters** | Import XML, édition en ligne, suppression |
| 🖼️ **Image de couverture** | Ajout/remplacement jaquette (JPG/PNG) |
| ⚙️ **Général** | Titre, numérotation personnalisée, suppression des tags |
| 🎵 **Audio Sync** | Synchronisation automatique par corrélation FFT (single file) |
| 🎵🎵 **Audio Sync Batch** | Idem en batch sur dossier entier |
| 🎥 **Frame Check** | Vérification frames/durée original vs encodé |
| 🖼️ **Extraire Images** | Extraction frames JPG/PNG/BMP avec contrôle qualité |
| 📊 **MediaInfo** | Analyse complète des pistes, chapitres, pièces jointes |
| 💾 **Préréglages** | Sauvegarde/chargement de configurations |
| 🔧 **Options** | Chemins mkvpropedit, mkvmerge, ffmpeg, ffprobe — thèmes clair/sombre |

### Fonctionnalités clés
- ✅ **Traitement batch** — des dizaines de fichiers en une opération
- ✅ **Drag & Drop** — glisser-déposer les fichiers MKV directement
- ✅ **Raccourcis clavier** — `Ctrl+O`, `Ctrl+Shift+O`, `Suppr`, `Ctrl+S`
- ✅ **Thème clair/sombre**
- ✅ **Export/Import des paramètres** en JSON
- ✅ **Audio Sync automatique** par corrélation FFT (numpy/scipy)
- ✅ **Extraction frame précise** par timecode ou numéro de frame
- ✅ **Logging** complet dans `pymkvpropedit.log`
- ✅ **Thread-safe** — UI non bloquée pendant le traitement

---

## 🚀 Installation Portable (Recommandé)

> **Aucune configuration requise** — double-cliquez et c'est parti.

1. Téléchargez la **dernière release** : [📦 PyMkvPropEdit v3.4](https://github.com/Crysisjim/PyMkvPropEdit/releases/latest)
2. Extrayez le ZIP dans le dossier de votre choix
3. Installez **[MKVToolNix](https://mkvtoolnix.download/)** si ce n'est pas déjà fait
4. (Optionnel) Installez **[FFmpeg](https://ffmpeg.org/download.html)** pour Audio Sync et Frame Extraction
5. Double-cliquez sur **`run.bat`**

Le launcher installe automatiquement les dépendances Python au premier démarrage.

---

## 📦 Prérequis

| Composant | Requis | Notes |
|-----------|--------|-------|
| **Windows** | ✅ Obligatoire | Windows 10/11 |
| **Python 3.10+** | ✅ Obligatoire | [python.org](https://www.python.org/) — cocher "Add to PATH" |
| **MKVToolNix** | ✅ Obligatoire | Fournit `mkvpropedit` et `mkvmerge` |
| **FFmpeg** | ⚠️ Recommandé | Pour Audio Sync et Frame Extraction |
| **numpy / scipy** | ⚠️ Recommandé | Pour Audio Sync automatique |
| **Pillow** | ✅ Auto-installé | Requis pour l'interface |
| **tkinterdnd2** | ⚠️ Optionnel | Pour le drag & drop (installé automatiquement) |

---

## 🔧 Installation Développeur (depuis les sources)

```bash
git clone https://github.com/Crysisjim/PyMkvPropEdit.git
cd PyMkvPropEdit
pip install -r requirements.txt
pythonw "PyMkvPropEdit v3.4.pyw"
```

---

## 🗂️ Structure du projet

```
PyMkvPropEdit/
├── PyMkvPropEdit v3.4.pyw   # Application principale
├── run.bat                  # Launcher portable (installe deps + lance)
├── requirements.txt         # Dépendances Python
├── vivi.ico                 # Icône de l'application
├── backroom.jpg             # Fond onglet "À propos"
├── success.jpg              # Image résumé succès
├── failure.jpg              # Image résumé échec
├── warning.jpg              # Image résumé avertissement
└── README.md
```

> **Générés automatiquement (non versionnés) :**
> `pymkvpropedit_settings.json`, `presets.json`, `pymkvpropedit.log`

---

## 🎵 Audio Sync — Comment ça marche ?

L'onglet **Audio Sync** utilise une **corrélation croisée FFT** (via scipy) pour calculer automatiquement le décalage temporel entre la piste audio de référence (ex: japonais) et les autres pistes.

1. Charger un fichier MKV
2. Définir la langue de référence (ex: `jpn`)
3. Cliquer **Lancer l'Analyse Auto**
4. Vérifier les délais calculés
5. Cliquer **Appliquer les Delays** → nouveau fichier `_SYNC.mkv` créé

> Le paramètre **Début analyse** permet d'analyser depuis n'importe quelle position (utile pour les OPs/EDs courts).

---

## 📅 Changelog complet

<details>
<summary>v3.3 — Audio Sync amélioré</summary>

- [FIX] Audio Sync: offset de début configurable (était hardcodé à 300s)
- [FIX] Audio Sync: auto-ajustement si fichier plus court qu'attendu
- [NEW] Champ "Début analyse" pour les fichiers courts (OPs/EDs)

</details>

<details>
<summary>v3.2 — Frame Extractor amélioré</summary>

- [NEW] Frame Extractor: contrôle qualité JPG (q:v 1-31) et PNG (compression 0-9)
- [NEW] Extraction frame précise par timecode (HH:MM:SS.ms) ou numéro de frame
- [NEW] Conversion numéro de frame → timecode via FPS détecté

</details>

<details>
<summary>v3.1 — Support fichiers raw</summary>

- [FIX] Support HEVC/H264/H265 raw (fallback durée multi-méthodes)
- [FIX] Utilisation des chemins FFmpeg/FFprobe configurés
- [FIX] Crash DnD sur bibliothèque tkdnd manquante (fallback gracieux)
- [NEW] Paramètres FFmpeg & FFprobe dans Options avec auto-détection
- [NEW] Support étendu: .hevc .h265 .264 .h264 .ivf .webm .ts

</details>

<details>
<summary>v3.0 — Refactoring majeur</summary>

- [FIX] Thread safety: toutes les mises à jour GUI depuis les threads via after()
- [FIX] Gestion exceptions propre + logging
- [FIX] tempfile.mktemp remplacé par NamedTemporaryFile
- [FIX] Chemins relatifs via APP_DIR
- [REFACTOR] run_hidden() helper centralisé
- [REFACTOR] AudioSyncMixin pour la logique partagée
- [NEW] Onglet MediaInfo
- [NEW] Barre de statut avec compteur de fichiers
- [NEW] Raccourcis clavier
- [NEW] Export/Import paramètres JSON
- [NEW] Logging vers fichier

</details>

---

## 🤝 Contribuer

Les contributions sont les bienvenues !

1. Forkez le projet
2. Créez votre branche (`git checkout -b feature/ma-fonctionnalite`)
3. Committez vos changements
4. Ouvrez une Pull Request

---

## 📄 Licence

MIT — Voir [LICENSE](LICENSE) pour les détails.

---

<div align="center">

**Fait avec ❤️ par [Crysisjim](https://github.com/Crysisjim)**

*Companion tool for [MKVToolNix](https://mkvtoolnix.download/) — the best MKV toolkit.*

</div>
