# 🗂️ Tabs Overview / Description des onglets

---

## Input / Output

| Onglet | Description FR | Description EN |
|--------|---------------|----------------|
| **Input** | Ajouter des fichiers MKV à traiter. Supporte le glisser-déposer. Réorganiser l'ordre avec ↑↓. | Add MKV files for processing. Supports drag & drop. Reorder with ↑↓. |
| **Output** | Log des opérations en temps réel. Sauvegardable en .txt. | Real-time operation log. Saveable as .txt. |

## Pistes / Tracks

| Onglet | Description FR | Description EN |
|--------|---------------|----------------|
| **Vidéo / Video** | Modifier nom, langue, flags pour chaque piste vidéo. | Edit name, language, flags for each video track. |
| **Audio** | Modifier nom, langue, default/forced pour chaque piste audio. | Edit name, language, default/forced for each audio track. |
| **Sous-titres / Subtitles** | Modifier nom, langue, flags pour chaque piste de sous-titres. | Edit name, language, flags for each subtitle track. |

> 💡 Cocher **"Edit Track"** pour activer la modification d'une piste. / Check **"Edit Track"** to enable editing for a track.

## Chapitres / Chapters

- **FR :** Charger un fichier XML de chapitres. Éditer les noms en double-cliquant. Ajouter/supprimer des chapitres. Option pour supprimer tous les chapitres du batch.
- **EN :** Load an XML chapter file. Edit names by double-clicking. Add/remove chapters. Option to delete all chapters from the batch.

## Image de couverture / Cover Image

- **FR :** Ajouter ou remplacer la jaquette (cover art) dans les fichiers MKV. Formats JPG et PNG. Prévisualisation de l'image sélectionnée.
- **EN :** Add or replace cover art in MKV files. JPG and PNG formats. Preview of selected image.

## Général / General

| Option | Description FR | Description EN |
|--------|---------------|----------------|
| **Titre** | Définir le titre de tous les fichiers du batch (supporte `{file_name}`) | Set title for all batch files (supports `{file_name}`) |
| **Numérotation** | Ajouter un numéro séquentiel au titre `[01] titre` | Add sequential number to title `[01] title` |
| **Supprimer tags** | Effacer tous les tags des fichiers MKV | Clear all tags from MKV files |
| **Paramètres extra** | Arguments supplémentaires passés à mkvpropedit | Extra arguments passed to mkvpropedit |

## Préréglages / Presets

- **FR :** Sauvegarder la configuration des pistes (nom, langue, flags) comme préréglage réutilisable. Charger, modifier, supprimer les préréglages.
- **EN :** Save track configuration (name, language, flags) as a reusable preset. Load, edit, delete presets.

## Options

| Paramètre | Description |
|-----------|-------------|
| **mkvpropedit** | Chemin vers l'exécutable / Path to executable |
| **mkvmerge** | Chemin vers l'exécutable / Path to executable |
| **FFmpeg** | Requis pour Audio Sync et Frame Extraction / Required for Audio Sync and Frame Extraction |
| **FFprobe** | Requis pour l'analyse / Required for analysis |
| **Thème** | Clair / Sombre — Light / Dark |
| **Langue** | 🇫🇷 Français / 🇬🇧 English (redémarrage requis / restart required) |
| **Sauvegarder pistes** | Mémoriser la config des pistes à la fermeture / Save track config on close |

## Audio Sync 🎵 / Audio Sync Batch 🎵🎵

→ Voir la page [Audio Sync](Audio-Sync) pour le guide complet.

## Frame Check 🎥

- **FR :** Comparer le nombre de frames et la durée entre fichiers originaux et encodés. Utile pour vérifier l'intégrité après encodage.
- **EN :** Compare frame count and duration between original and encoded files. Useful to verify integrity after encoding.

## Extraire Images / Extract Frames 🖼️

| Fonctionnalité | Description FR | Description EN |
|----------------|---------------|----------------|
| **Formats** | JPG, PNG, BMP | JPG, PNG, BMP |
| **Qualité JPG** | Slider q:v 1 (meilleur) à 31 (pire) | Slider q:v 1 (best) to 31 (worst) |
| **Compression PNG** | Slider 0 (rapide) à 9 (max) | Slider 0 (fast) to 9 (max) |
| **Mode** | Toutes les frames OU une par intervalle (sec) | All frames OR one per interval (sec) |
| **Frame précise** | Par timecode `HH:MM:SS.ms` ou numéro de frame | By timecode `HH:MM:SS.ms` or frame number |

## MediaInfo 📊

- **FR :** Analyse rapide d'un fichier MKV : toutes les pistes (codec, langue, résolution, canaux audio), chapitres, pièces jointes. Arborescence interactive.
- **EN :** Quick MKV file analysis: all tracks (codec, language, resolution, audio channels), chapters, attachments. Interactive tree view.
