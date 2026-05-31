#!/usr/bin/env python3
"""
PyMkvPropEdit v3.7 - Batch GUI pour mkvpropedit
Refactored with improvements and new features.

Changelog v3.7:
- [NEW] Batch Pro tab: auto-rename (TVDB/TMDB/TVmaze) + track reorder + sync pipeline
- [NEW] Filename parser (series/movie detection, season/episode/year)
- [NEW] Video metadata detection (resolution/codec/HDR) for movie naming
- [NEW] Single-pass mkvmerge combining --sync + --track-order
- [NEW] TVDB/TMDB API keys in Options (stored locally)

Changelog v3.6:
- [NEW] First-launch wizard: choose between system MKVToolNix or bundled MKVToolNix
- [NEW] Bundled MKVToolNix binaries (mkvpropedit, mkvmerge, mkvextract) — 100% standalone EXE
- [NEW] Portable EXE version: no Python required, all dependencies bundled
- [FIX] VERSION bump 3.5 → 3.6

Changelog v3.5:
- [NEW] Bilingual EN/FR UI — language toggle in Options tab (restart to apply)
- [NEW] Windows 11 toast notifications after batch processing, audio sync, frame extraction
- [NEW] win11toast integration (optional dependency)

Changelog v3.4:
- [FIX] sanitize_input: ne supprime plus les apostrophes (noms de pistes français corrects)
- [FIX] calculate_delay: garde contre tableau vide (évite crash scipy)
- [FIX] process_analysis: duration_var sans try/except → ValueError handled
- [FIX] MediaInfo: boucle chapitres morte réparée, affiche désormais le nombre de chapitres
- [FIX] _apply_chapter_names: NamedTemporaryFile handle explicitement fermé (PermissionError Windows)
- [FIX] _apply_chapter_names: ET.tostring(encoding='unicode', xml_declaration=True) → ValueError Python 3.8+
- [FIX] cover.jpg hardcodé ignorait le champ "Nom de la pièce jointe" dans l'UI
- [FIX] Thread safety: process_files() ne bloque plus le thread principal (UI responsive)
- [FIX] _validate_track_indices: warning visible dans l'Output en cas d'exception

Changelog v3.3:
- [FIX] Audio Sync: configurable analysis start offset (was hardcoded to 300s/5min)
- [FIX] Audio Sync: auto-adjusts start position and duration if file is shorter than expected
- [NEW] Audio Sync: new "Début analyse" field works for short files (mini-episodes, OPs/EDs)

Changelog v3.2:
- [NEW] Frame Extractor: quality controls (JPG q:v slider 1-31, PNG compression slider 0-9)
- [NEW] Frame Extractor: extract single precise frame by timecode (HH:MM:SS.ms) or frame number
- [NEW] Frame number auto-conversion to timecode via detected FPS

Changelog v3.1:
- [FIX] Frame Extractor: support raw HEVC/H264/H265 files (multi-fallback duration detection)
- [FIX] Frame Extractor: uses configured FFmpeg path instead of hardcoded "ffmpeg"
- [FIX] All ffprobe/ffmpeg calls now use configurable paths from Options
- [FIX] DnD crash on missing tkdnd native library (graceful fallback)
- [NEW] FFmpeg & FFprobe path settings in Options tab with auto-detection
- [NEW] Extended video file support (.hevc .h265 .264 .h264 .ivf .webm .ts)

Changelog v3.0:
- [FIX] Thread safety: all GUI updates from threads now use after()
- [FIX] Replaced bare except: with proper exception handling + logging
- [FIX] Replaced deprecated tempfile.mktemp with NamedTemporaryFile
- [FIX] Relative paths resolved via APP_DIR (icons, settings, presets)
- [REFACTOR] Extracted run_hidden() subprocess helper (no more copy-paste)
- [REFACTOR] Extracted AudioSyncMixin for shared sync logic
- [REFACTOR] Deduplicated get_file_info track iteration
- [REFACTOR] Centralized startupinfo creation
- [NEW] MediaInfo Tab: quick file analysis with full track details
- [NEW] Status bar with file count and processing state
- [NEW] Keyboard shortcuts (Ctrl+O, Ctrl+Shift+O, Del, Ctrl+S)
- [NEW] Export/Import settings as shareable .json
- [NEW] Logging to file (pymkvpropedit.log) for debugging
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import tempfile
import wave
import logging
import queue

# Imports pour la synchro
try:
    import numpy as np
    from scipy import signal
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

import os
import subprocess
import json
import shlex
from tkinter import scrolledtext
import glob
import xml.etree.ElementTree as ET
from PIL import Image, ImageTk
import uuid
import shutil
import re
import time
import urllib.request
import urllib.parse
import urllib.error

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None

from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================================
# CONSTANTS & CONFIG
# ============================================================================

import sys as _sys
# Handle PyInstaller frozen mode
if getattr(_sys, 'frozen', False):
    APP_DIR = os.path.dirname(_sys.executable)
    _ASSET_DIR = getattr(_sys, '_MEIPASS', APP_DIR)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    _ASSET_DIR = APP_DIR
VERSION = "3.7"

SETTINGS_FILE = os.path.join(APP_DIR, "pymkvpropedit_settings.json")
PRESETS_FILE = os.path.join(APP_DIR, "presets.json")
LOG_FILE = os.path.join(APP_DIR, "pymkvpropedit.log")

# XML 1.0 invalid control chars (C0 except tab/LF/CR, DEL, C1 controls, BOM/non-chars).
# A single one of these anywhere makes mkvpropedit reject the WHOLE tags XML,
# so all tags silently disappear while attachments still get added.
_XML_INVALID_BYTES = (
    list(range(0x00, 0x09)) + [0x0b, 0x0c] + list(range(0x0e, 0x20)) +
    list(range(0x7f, 0xa0)) + list(range(0x200b, 0x2010)) +
    [0x2028, 0x2029] + list(range(0x202a, 0x202f)) +
    [0x2060, 0xfeff, 0xfffe, 0xffff]
)
_XML_INVALID_RE = re.compile('[' + ''.join(chr(c) for c in _XML_INVALID_BYTES) + ']')


def xml_safe_text(text):
    """Strip XML-invalid / invisible control chars so mkvpropedit accepts the tags."""
    if not text:
        return text
    return _XML_INVALID_RE.sub('', str(text)).strip()


LANGUAGES = [
    'eng (English)', 'fra (French)', 'jpn (Japanese)', 'spa (Spanish)', 'deu (German)',
    'ita (Italian)', 'por (Portuguese)', 'rus (Russian)', 'chi (Chinese)', 'ara (Arabic)',
    'hin (Hindi)', 'kor (Korean)', 'pol (Polish)', 'nld (Dutch)', 'swe (Swedish)',
    'tur (Turkish)', 'vie (Vietnamese)', 'tha (Thai)', 'ces (Czech)', 'hun (Hungarian)',
    'ron (Romanian)', 'ukr (Ukrainian)', 'und (Undetermined)'
]

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
# Silence noisy 3rd-party debug loggers
for _noisy in ('PIL', 'PIL.TiffImagePlugin', 'PIL.Image', 'asyncio', 'win11toast'):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
logger = logging.getLogger("PyMkvPropEdit")

# ============================================================================
# WIN11TOAST — Notifications Windows 11
# ============================================================================

try:
    from win11toast import toast as _win11toast
    HAS_WIN11TOAST = True
except ImportError:
    HAS_WIN11TOAST = False


_notifications_enabled: bool = True  # updated from settings at app startup


def notify_toast(title, body):
    if not _notifications_enabled or not HAS_WIN11TOAST:
        return
    try:
        # PNG gives better quality in win11toast than ICO
        icon_path = resolve_asset("vivi.png")
        if not os.path.exists(icon_path):
            icon_path = resolve_asset("vivi.ico")
        if not os.path.exists(icon_path):
            icon_path = None
        kwargs = {'app_id': f'PyMkvPropEdit v{VERSION}'}
        if icon_path:
            kwargs['icon'] = {'src': icon_path, 'placement': 'appLogoOverride'}
        _win11toast(title, body, **kwargs)
    except Exception as e:
        logger.debug(f"Toast notification failed: {e}")


# ============================================================================
# INTERNATIONALIZATION (EN / FR)
# ============================================================================

# Early lang load — before UI creation
_early_settings: dict = {}
if os.path.exists(SETTINGS_FILE):
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as _f:
            _early_settings = json.load(_f)
    except Exception:
        pass
LANG: str = _early_settings.get('language', 'fr')

STRINGS: dict = {
    'fr': {
        # Tabs
        'tab_input': 'Input', 'tab_output': 'Output',
        'tab_video': 'Vidéo', 'tab_audio': 'Audio', 'tab_subtitle': 'Sous-titres',
        'tab_chapters': 'Chapitres', 'tab_cover': 'Image de couverture',
        'tab_general': 'Général', 'tab_presets': 'Préréglages', 'tab_options': 'Options',
        'tab_sync': 'Audio Sync 🎵', 'tab_sync_batch': 'Audio Sync Batch 🎵🎵',
        'tab_frame_check': 'Frame Check 🎥', 'tab_extract': 'Extraire Images 🖼️',
        'tab_mediainfo': 'MediaInfo 📊', 'tab_about': 'À propos',
        # Main buttons
        'btn_add_files': 'Ajouter Fichiers 📄', 'btn_add_folder': 'Ajouter Dossier 📁',
        'btn_remove': 'Supprimer Sélectionnés 🗑️', 'btn_clear': 'Vider ❌',
        'btn_move_up': 'Move Up ↑', 'btn_move_down': 'Move Down ↓',
        'btn_process': 'Process Files 🚀', 'btn_cancel': 'Cancel 🛑',
        'btn_open': 'Ouvrir', 'btn_browse': 'Parcourir',
        'btn_open_mkv': 'Ouvrir MKV', 'btn_analyze': "Lancer l'Analyse Auto 🔍",
        'btn_apply_delays': 'Appliquer les Delays au fichier 💾',
        'btn_start_batch': 'Lancer le Batch 🔍',
        'btn_verify': 'Lancer la Vérification 🔍',
        'btn_extract': "Lancer l'Extraction 🚀", 'btn_stop': 'STOP 🛑',
        'btn_extract_frame': '📸 Extraire cette frame',
        'btn_load_edit': 'Charger & Éditer',
        'btn_add_chapter': 'Ajouter chapitre', 'btn_del_chapter': 'Supprimer chapitre',
        'btn_browse_image': "Parcourir l'image",
        'btn_save_preset': 'Sauvegarder', 'btn_load_preset': 'Charger', 'btn_del_preset': 'Supprimer',
        'btn_export_settings': 'Exporter paramètres 📤', 'btn_import_settings': 'Importer paramètres 📥',
        'btn_save_log': 'Sauvegarder Log', 'btn_analyze_file': 'Analyser 🔍',
        # Labels — Audio sync
        'lbl_select_mkv': ' 1. Sélectionner le fichier MKV (Source complète) ',
        'lbl_ref_lang': 'Langue de Référence (Jap) :', 'lbl_duration': "Durée d'analyse (sec) :",
        'lbl_start_offset': 'Début analyse (sec) :',
        'lbl_start_offset_hint': '(0=début, ajusté auto si trop grand)',
        'lbl_batch_start': 'Début (sec) :', 'lbl_start_hint_short': '(0=début)',
        'chk_apply_subs': 'Appliquer automatiquement le délai aux sous-titres de même langue',
        'chk_apply_subs_short': 'Appliquer aux sous-titres',
        'chk_apply_props': 'Appliquer les paramètres mkvpropedit définis',
        'lbl_waiting': 'En attente de fichier...', 'lbl_file_loaded': 'Fichier chargé. Cliquez sur Analyse.',
        # Tree columns
        'col_lang': 'Langue', 'col_name': 'Nom de la piste', 'col_status': 'État', 'col_delay': 'Delay Trouvé',
        # Frame check
        'lbl_ori_files': 'Fichiers Originaux (Source)', 'lbl_enc_files': 'Fichiers Encodés (A vérifier)',
        'btn_add_ori': 'Ajouter Fichiers Ori 📄', 'btn_add_ori_folder': 'Ajouter Dossier Ori 📁',
        'btn_clear_ori': 'Vider Ori ❌', 'btn_add_enc': 'Ajouter Fichiers Enc 📄',
        'btn_add_enc_folder': 'Ajouter Dossier Enc 📁', 'btn_clear_enc': 'Vider Enc ❌',
        'lbl_tolerance': 'Tolérance durée (sec) :',
        # Frame extract
        'lbl_video_source': ' 1. Source Vidéo ', 'lbl_params_dest': ' 2. Paramètres & Destination ',
        'lbl_format': 'Format :', 'chk_auto_folder': 'Créer un sous-dossier au nom de la vidéo',
        'lbl_manual_dir': 'Ou dossier manuel :', 'lbl_quality_frame': ' Qualité ',
        'lbl_jpg_quality': 'JPG (q:v 1=best 31=worst) :', 'lbl_png_compression': 'PNG (0=fast 9=max compress) :',
        'lbl_frequency': 'Fréquence :', 'rb_interval': 'Intervalle (sec)', 'rb_all_frames': 'Toutes les frames',
        'rb_frame_range': 'Plage frames', 'lbl_from_frame': 'Frame N°', 'lbl_to_frame': 'à N°',
        'lbl_every': '-> Une image toutes les :', 'lbl_seconds': 'secondes',
        'lbl_single_frame_section': ' Extraire une frame précise ',
        'lbl_timecode': 'Timecode (HH:MM:SS.ms) :', 'lbl_frame_num': 'ou Frame N° :',
        'lbl_ready': 'Prêt',
        # Chapters tab
        'lbl_chapters_file': 'Fichier de chapitres (XML):', 'lbl_suffix': 'Suffixe:',
        'chk_remove_chapters': 'Supprimer les chapitres',
        'chk_apply_chapter_names': 'Appliquer les noms de chapitres à tous les fichiers',
        # Cover tab
        'lbl_cover_intro': 'Ajouter une image de couverture (Jaquette) aux fichiers MKV :',
        'lbl_select_image': 'Sélectionner une image :', 'lbl_no_preview': 'Aucun aperçu disponible',
        'lbl_attachment_name': 'Nom de la pièce jointe :', 'lbl_cover_format': 'Format :',
        # General tab
        'lbl_title_field': 'Titre :', 'chk_custom_numbering': 'Numérotation personnalisée',
        'lbl_start_num': 'Numéro de départ :', 'lbl_padding': 'Remplissage :',
        'chk_delete_tags': 'Supprimer tous les tags', 'lbl_extra_params': 'Paramètres supplémentaires :',
        # Presets tab
        'lbl_preset_name': 'Nom du préréglage :', 'lbl_select_preset': 'Sélectionner un préréglage :',
        # Options
        'lbl_theme': 'Thème :', 'lbl_theme_light': 'Clair', 'lbl_theme_dark': 'Sombre',
        'lbl_save_tracks': 'Sauvegarder les configurations des pistes',
        'lbl_language_app': 'Langue / Language :',
        'lbl_restart_required': '(redémarrage requis / restart required)',
        'lbl_mkvpropedit_path': 'Chemin de mkvpropedit :',
        'lbl_mkvmerge_path': 'Chemin de mkvmerge :',
        'lbl_ffmpeg_path': 'Chemin de FFmpeg :', 'lbl_ffprobe_path': 'Chemin de FFprobe :',
        # Output tab
        'chk_detailed': 'Informations détaillées',
        # Status bar
        'status_ready': f'PyMkvPropEdit v{VERSION} — Prêt',
        'status_files': '{n} fichier(s) chargé(s)', 'status_processing': 'Traitement de {n} fichier(s) en cours...',
        # Notifications
        'notif_batch_done': 'Traitement terminé', 'notif_batch_body': '{s} succès — {e} erreur(s)',
        'notif_sync_done': 'Audio Sync terminé', 'notif_sync_body': 'Batch sync terminé.',
        'notif_extract_done': 'Extraction terminée', 'notif_extract_body': 'Images extraites dans le dossier de sortie.',
        # numpy missing
        'warn_no_scipy': '⚠️ Modules numpy/scipy manquants.', 'warn_install_scipy': 'Installez-les via : pip install numpy scipy',
        # First launch wizard
        'wizard_title': 'Premier lancement — Configuration',
        'wizard_lang_section': '🌐 Langue / Language',
        'wizard_mkv_section': '🔧 MKVToolNix',
        'wizard_msg': 'Choisissez comment utiliser les outils MKVToolNix :',
        'wizard_system': 'MKVToolNix système\n(utiliser la version installée sur votre PC)',
        'wizard_bundled': 'MKVToolNix intégré\n(inclus dans l\'app, aucune installation requise)',
        'wizard_bundled_unavail': '(non disponible dans cette version)',
        'wizard_confirm': 'Confirmer',
        'wizard_restart_needed': '⚠️ Redémarrage requis pour appliquer la langue.',
        'wizard_ffmpeg_section': '🎬 FFmpeg',
        'wizard_ffmpeg_found': 'Installations FFmpeg détectées :',
        'wizard_ffmpeg_none': 'Aucun FFmpeg détecté. Cliquez Parcourir pour en sélectionner un manuellement.',
        'wizard_ffmpeg_scanning': '🔍 Recherche de FFmpeg en cours...',
        'wizard_ffmpeg_browse': 'Parcourir...',
        # Options MKV switch
        'btn_use_bundled': '🔄 Utiliser MKVToolNix intégré',
        'btn_use_system': '🔄 Utiliser MKVToolNix système',
        'lbl_mkvtools_section': 'MKVToolNix',
        'msg_switched_bundled': 'MKVToolNix intégré activé. Chemins mis à jour.',
        'msg_no_bundled': 'MKVToolNix intégré non disponible dans cette version.',
        'lbl_notifications': '🔔 Notifications Windows 11 (win11toast)',
        'summary_title': 'Résumé du Traitement',
        'summary_success': 'Succès',
        'summary_errors': 'Erreurs',
        'summary_duration': 'Durée',
        'summary_see_errors': 'Voir les erreurs',
        'summary_errors_title': 'Fichiers en Erreur',
        'summary_caption_success': 'Strike! Victory!',
        'summary_caption_warning': 'Attention !',
        'summary_caption_failure': 'Échec...',
        # Batch Pro tab
        'tab_batchpro': 'Batch Pro 🚀',
        'bp_step1': '① Fichiers',
        'bp_step2': '② Renommage Auto (TVDB / TMDB / TVmaze)',
        'bp_step3': '③ Ordre des pistes',
        'bp_step4': '④ Pipeline & Exécution',
        'bp_search_names': '🔍 Rechercher les noms',
        'bp_col_file': 'Fichier original',
        'bp_col_detected': 'Détecté',
        'bp_col_newname': 'Nouveau nom',
        'bp_col_status': 'Statut',
        'bp_lang_search': 'Langue recherche :',
        'bp_chk_sync': 'Synchroniser audio',
        'bp_chk_props': 'Appliquer paramètres mkvpropedit',
        'bp_chk_reorder': 'Réordonner les pistes',
        'bp_chk_rename': 'Renommer fichier (nom auto)',
        'bp_run': '🚀 Lancer le pipeline complet',
        'bp_load_ref': 'Charger fichier référence',
        'bp_track_up': '↑ Monter',
        'bp_track_down': '↓ Descendre',
        'bp_save_template': '💾 Enregistrer modèle',
        'bp_reorder_hint': 'Définissez l\'ordre voulu. Appliqué à tous les fichiers (matching type+langue+forced).',
        'bp_no_apikey': 'Aucune clé API configurée — utilisation de TVmaze (séries uniquement). Configurez TVDB/TMDB dans Options.',
        'bp_load_first': '📂 Premier fichier de la liste',
        'bp_chk_embed_meta': 'Intégrer métadonnées (tags + cover art)',
        'bp_pick_meta': 'Choisir sources métadonnées',
        'bp_picker_title': 'Sélectionner illustration / description',
        'bp_picker_cover': 'Illustration',
        'bp_picker_desc': 'Description courte',
        'bp_picker_synopsis': 'Synopsis long',
        'bp_picker_apply_all': 'Appliquer ce choix à tous les fichiers de la liste',
        'bp_picker_loading': 'Chargement...',
        'bp_picker_cast': 'Cast / Artiste',
        'bp_picker_genres': 'Genres',
        'bp_searching': 'Recherche en cours...',
        'bp_search_done': 'Recherche terminée.',
        'bp_choose': 'Choisir...',
        'bp_pick_match': 'Sélectionner la correspondance',
        'bp_col_track': 'Piste', 'bp_col_type': 'Type', 'bp_col_lang': 'Langue',
        'bp_col_name_tr': 'Nom', 'bp_col_forced': 'Forcé',
        'bp_col_codec': 'Codec', 'bp_col_default': 'Défaut',
        'bp_chk_preserve': 'Conserver source (mode copie)',
        'lbl_tvdb_key': 'Clé API TheTVDB :',
        'lbl_tmdb_key': 'Clé API TMDB :',
    },
    'en': {
        # Tabs
        'tab_input': 'Input', 'tab_output': 'Output',
        'tab_video': 'Video', 'tab_audio': 'Audio', 'tab_subtitle': 'Subtitles',
        'tab_chapters': 'Chapters', 'tab_cover': 'Cover Image',
        'tab_general': 'General', 'tab_presets': 'Presets', 'tab_options': 'Options',
        'tab_sync': 'Audio Sync 🎵', 'tab_sync_batch': 'Audio Sync Batch 🎵🎵',
        'tab_frame_check': 'Frame Check 🎥', 'tab_extract': 'Extract Frames 🖼️',
        'tab_mediainfo': 'MediaInfo 📊', 'tab_about': 'About',
        # Main buttons
        'btn_add_files': 'Add Files 📄', 'btn_add_folder': 'Add Folder 📁',
        'btn_remove': 'Remove Selected 🗑️', 'btn_clear': 'Clear ❌',
        'btn_move_up': 'Move Up ↑', 'btn_move_down': 'Move Down ↓',
        'btn_process': 'Process Files 🚀', 'btn_cancel': 'Cancel 🛑',
        'btn_open': 'Open', 'btn_browse': 'Browse',
        'btn_open_mkv': 'Open MKV', 'btn_analyze': 'Start Auto Analysis 🔍',
        'btn_apply_delays': 'Apply Delays to File 💾',
        'btn_start_batch': 'Start Batch 🔍',
        'btn_verify': 'Start Verification 🔍',
        'btn_extract': 'Start Extraction 🚀', 'btn_stop': 'STOP 🛑',
        'btn_extract_frame': '📸 Extract this frame',
        'btn_load_edit': 'Load & Edit',
        'btn_add_chapter': 'Add chapter', 'btn_del_chapter': 'Remove chapter',
        'btn_browse_image': 'Browse image',
        'btn_save_preset': 'Save', 'btn_load_preset': 'Load', 'btn_del_preset': 'Delete',
        'btn_export_settings': 'Export settings 📤', 'btn_import_settings': 'Import settings 📥',
        'btn_save_log': 'Save Log', 'btn_analyze_file': 'Analyze 🔍',
        # Labels — Audio sync
        'lbl_select_mkv': ' 1. Select MKV File (Full source) ',
        'lbl_ref_lang': 'Reference Language (Jpn):', 'lbl_duration': 'Analysis Duration (sec):',
        'lbl_start_offset': 'Analysis Start (sec):',
        'lbl_start_offset_hint': '(0=start, auto-adjusted if too large)',
        'lbl_batch_start': 'Start (sec):', 'lbl_start_hint_short': '(0=start)',
        'chk_apply_subs': 'Auto-apply delay to subtitles of same language',
        'chk_apply_subs_short': 'Apply to subtitles',
        'chk_apply_props': 'Apply defined mkvpropedit settings',
        'lbl_waiting': 'Waiting for file...', 'lbl_file_loaded': 'File loaded. Click Analyze.',
        # Tree columns
        'col_lang': 'Language', 'col_name': 'Track Name', 'col_status': 'Status', 'col_delay': 'Delay Found',
        # Frame check
        'lbl_ori_files': 'Original Files (Source)', 'lbl_enc_files': 'Encoded Files (To verify)',
        'btn_add_ori': 'Add Original Files 📄', 'btn_add_ori_folder': 'Add Original Folder 📁',
        'btn_clear_ori': 'Clear Originals ❌', 'btn_add_enc': 'Add Encoded Files 📄',
        'btn_add_enc_folder': 'Add Encoded Folder 📁', 'btn_clear_enc': 'Clear Encoded ❌',
        'lbl_tolerance': 'Duration tolerance (sec):',
        # Frame extract
        'lbl_video_source': ' 1. Video Source ', 'lbl_params_dest': ' 2. Parameters & Destination ',
        'lbl_format': 'Format:', 'chk_auto_folder': 'Create a subfolder named after the video',
        'lbl_manual_dir': 'Or manual folder:', 'lbl_quality_frame': ' Quality ',
        'lbl_jpg_quality': 'JPG (q:v 1=best 31=worst):', 'lbl_png_compression': 'PNG (0=fast 9=max compress):',
        'lbl_frequency': 'Frequency:', 'rb_interval': 'Interval (sec)', 'rb_all_frames': 'All frames',
        'rb_frame_range': 'Frame range', 'lbl_from_frame': 'Frame N°', 'lbl_to_frame': 'to N°',
        'lbl_every': '-> One image every:', 'lbl_seconds': 'seconds',
        'lbl_single_frame_section': ' Extract a specific frame ',
        'lbl_timecode': 'Timecode (HH:MM:SS.ms):', 'lbl_frame_num': 'or Frame N°:',
        'lbl_ready': 'Ready',
        # Chapters tab
        'lbl_chapters_file': 'Chapter file (XML):', 'lbl_suffix': 'Suffix:',
        'chk_remove_chapters': 'Remove chapters',
        'chk_apply_chapter_names': 'Apply chapter names to all files',
        # Cover tab
        'lbl_cover_intro': 'Add a cover image (jacket) to MKV files:',
        'lbl_select_image': 'Select an image:', 'lbl_no_preview': 'No preview available',
        'lbl_attachment_name': 'Attachment name:', 'lbl_cover_format': 'Format:',
        # General tab
        'lbl_title_field': 'Title:', 'chk_custom_numbering': 'Custom numbering',
        'lbl_start_num': 'Start number:', 'lbl_padding': 'Padding:',
        'chk_delete_tags': 'Delete all tags', 'lbl_extra_params': 'Extra parameters:',
        # Presets tab
        'lbl_preset_name': 'Preset name:', 'lbl_select_preset': 'Select a preset:',
        # Options
        'lbl_theme': 'Theme:', 'lbl_theme_light': 'Light', 'lbl_theme_dark': 'Dark',
        'lbl_save_tracks': 'Save track configurations',
        'lbl_language_app': 'Langue / Language:',
        'lbl_restart_required': '(restart required / redémarrage requis)',
        'lbl_mkvpropedit_path': 'mkvpropedit path:',
        'lbl_mkvmerge_path': 'mkvmerge path:',
        'lbl_ffmpeg_path': 'FFmpeg path:', 'lbl_ffprobe_path': 'FFprobe path:',
        # Output tab
        'chk_detailed': 'Detailed information',
        # Status bar
        'status_ready': f'PyMkvPropEdit v{VERSION} — Ready',
        'status_files': '{n} file(s) loaded', 'status_processing': 'Processing {n} file(s)...',
        # Notifications
        'notif_batch_done': 'Processing complete', 'notif_batch_body': '{s} success — {e} error(s)',
        'notif_sync_done': 'Audio Sync complete', 'notif_sync_body': 'Batch sync finished.',
        'notif_extract_done': 'Extraction complete', 'notif_extract_body': 'Frames extracted to output folder.',
        # numpy missing
        'warn_no_scipy': '⚠️ numpy/scipy modules missing.', 'warn_install_scipy': 'Install via: pip install numpy scipy',
        'lbl_theme': 'Theme:', 'lbl_theme_light': 'Light', 'lbl_theme_dark': 'Dark',
        'lbl_save_tracks': 'Save track configurations',
        'lbl_language_app': 'Langue / Language:',
        'lbl_restart_required': '(restart required / redémarrage requis)',
        'lbl_mkvpropedit_path': 'mkvpropedit path:',
        'lbl_mkvmerge_path': 'mkvmerge path:',
        'lbl_ffmpeg_path': 'FFmpeg path:', 'lbl_ffprobe_path': 'FFprobe path:',
        'notif_batch_done': 'Processing complete',
        'notif_batch_body': '{s} success — {e} error(s)',
        'notif_sync_done': 'Audio Sync complete',
        'notif_sync_body': 'Batch sync finished.',
        'notif_extract_done': 'Extraction complete',
        'notif_extract_body': 'Frames extracted to output folder.',
        # First launch wizard
        'wizard_title': 'First Launch — Configuration',
        'wizard_lang_section': '🌐 Langue / Language',
        'wizard_mkv_section': '🔧 MKVToolNix',
        'wizard_msg': 'Choose how to use MKVToolNix tools:',
        'wizard_system': 'System MKVToolNix\n(use the version installed on your PC)',
        'wizard_bundled': 'Bundled MKVToolNix\n(included in the app, no installation needed)',
        'wizard_bundled_unavail': '(not available in this build)',
        'wizard_confirm': 'Confirm',
        'wizard_restart_needed': '⚠️ Restart required to apply language change.',
        'wizard_ffmpeg_section': '🎬 FFmpeg',
        'wizard_ffmpeg_found': 'Detected FFmpeg installations:',
        'wizard_ffmpeg_none': 'No FFmpeg detected. Click Browse to select one manually.',
        'wizard_ffmpeg_scanning': '🔍 Scanning for FFmpeg...',
        'wizard_ffmpeg_browse': 'Browse...',
        # Options MKV switch
        'btn_use_bundled': '🔄 Use Bundled MKVToolNix',
        'btn_use_system': '🔄 Use System MKVToolNix',
        'lbl_mkvtools_section': 'MKVToolNix',
        'msg_switched_bundled': 'Bundled MKVToolNix activated. Paths updated.',
        'msg_no_bundled': 'Bundled MKVToolNix not available in this build.',
        'lbl_notifications': '🔔 Windows 11 Notifications (win11toast)',
        'summary_title': 'Processing Summary',
        'summary_success': 'Success',
        'summary_errors': 'Errors',
        'summary_duration': 'Duration',
        'summary_see_errors': 'Show errors',
        'summary_errors_title': 'Files with Errors',
        'summary_caption_success': 'Strike! Victory!',
        'summary_caption_warning': 'Warning!',
        'summary_caption_failure': 'Failed...',
        # Batch Pro tab
        'tab_batchpro': 'Batch Pro 🚀',
        'bp_step1': '① Files',
        'bp_step2': '② Auto-Rename (TVDB / TMDB / TVmaze)',
        'bp_step3': '③ Track Order',
        'bp_step4': '④ Pipeline & Execution',
        'bp_search_names': '🔍 Search names',
        'bp_col_file': 'Original file',
        'bp_col_detected': 'Detected',
        'bp_col_newname': 'New name',
        'bp_col_status': 'Status',
        'bp_lang_search': 'Search language:',
        'bp_chk_sync': 'Sync audio',
        'bp_chk_props': 'Apply mkvpropedit settings',
        'bp_chk_reorder': 'Reorder tracks',
        'bp_chk_rename': 'Rename file (auto name)',
        'bp_run': '🚀 Run full pipeline',
        'bp_load_ref': 'Load reference file',
        'bp_track_up': '↑ Up',
        'bp_track_down': '↓ Down',
        'bp_save_template': '💾 Save template',
        'bp_reorder_hint': 'Define the desired order. Applied to all files (matching type+lang+forced).',
        'bp_no_apikey': 'No API key configured — using TVmaze (series only). Configure TVDB/TMDB in Options.',
        'bp_load_first': '📂 First file in list',
        'bp_chk_embed_meta': 'Embed metadata (tags + cover art)',
        'bp_pick_meta': 'Choose metadata sources',
        'bp_picker_title': 'Select cover / description',
        'bp_picker_cover': 'Cover art',
        'bp_picker_desc': 'Short description',
        'bp_picker_synopsis': 'Long synopsis',
        'bp_picker_apply_all': 'Apply this choice to all files in the list',
        'bp_picker_loading': 'Loading...',
        'bp_picker_cast': 'Cast / Artist',
        'bp_picker_genres': 'Genres',
        'bp_searching': 'Searching...',
        'bp_search_done': 'Search complete.',
        'bp_choose': 'Choose...',
        'bp_pick_match': 'Select match',
        'bp_col_track': 'Track', 'bp_col_type': 'Type', 'bp_col_lang': 'Language',
        'bp_col_name_tr': 'Name', 'bp_col_forced': 'Forced',
        'bp_col_codec': 'Codec', 'bp_col_default': 'Default',
        'bp_chk_preserve': 'Preserve source (copy mode)',
        'lbl_tvdb_key': 'TheTVDB API key:',
        'lbl_tmdb_key': 'TMDB API key:',
    }
}


def T(key: str) -> str:
    return STRINGS.get(LANG, STRINGS['fr']).get(key, STRINGS['fr'].get(key, key))


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_startupinfo():
    """Return STARTUPINFO to hide console windows on Windows."""
    if os.name == 'nt':
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return si
    return None


def run_hidden(cmd, **kwargs):
    """Run a subprocess with hidden console window on Windows.
    
    Wraps subprocess.run with proper startupinfo and encoding defaults.
    Returns the CompletedProcess result.
    """
    defaults = {
        'capture_output': True,
        'text': True,
        'encoding': 'utf-8',
        'startupinfo': get_startupinfo(),
    }
    defaults.update(kwargs)
    logger.debug(f"Running: {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, **defaults)


def popen_hidden(cmd, **kwargs):
    """Open a subprocess with hidden console window on Windows.
    
    Wraps subprocess.Popen with proper startupinfo and encoding defaults.
    Returns the Popen object.
    """
    defaults = {
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
        'text': True,
        'encoding': 'utf-8',
        'errors': 'replace',
        'startupinfo': get_startupinfo(),
    }
    defaults.update(kwargs)
    return subprocess.Popen(cmd, **defaults)


def make_temp_wav():
    """Create a temporary WAV file safely (replaces deprecated mktemp)."""
    f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    path = f.name
    f.close()
    return path


def safe_remove(path):
    """Remove a file if it exists, ignoring errors."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError as e:
        logger.warning(f"Could not remove {path}: {e}")


def sanitize_input(text):
    """Sanitize user input to prevent shell injection."""
    return re.sub(r'[;\n\r]', '', text.strip())


def resolve_asset(filename):
    """Resolve path to an asset file — handles PyInstaller frozen builds."""
    p = os.path.join(_ASSET_DIR, filename)
    if os.path.exists(p):
        return p
    return os.path.join(APP_DIR, filename)


def find_ffmpeg():
    """Find ffmpeg executable: check PATH, common locations."""
    found = shutil.which('ffmpeg')
    if found:
        return found
    # Common Windows locations
    for p in [r'C:\ffmpeg\bin\ffmpeg.exe', r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
              os.path.join(APP_DIR, 'ffmpeg.exe'), os.path.join(APP_DIR, 'ffmpeg', 'ffmpeg.exe')]:
        if os.path.exists(p):
            return p
    return 'ffmpeg'


def find_ffprobe():
    """Find ffprobe executable: check PATH, common locations."""
    found = shutil.which('ffprobe')
    if found:
        return found
    for p in [r'C:\ffmpeg\bin\ffprobe.exe', r'C:\Program Files\ffmpeg\bin\ffprobe.exe',
              os.path.join(APP_DIR, 'ffprobe.exe'), os.path.join(APP_DIR, 'ffmpeg', 'ffprobe.exe')]:
        if os.path.exists(p):
            return p
    return 'ffprobe'


def find_system_mkv_tool(tool_name: str) -> str:
    """Find a MKVToolNix tool: check PATH, then common Windows install dirs."""
    found = shutil.which(tool_name)
    if found:
        return found
    exe = f'{tool_name}.exe'
    for d in [
        r'C:\Program Files\MKVToolNix',
        r'C:\Program Files (x86)\MKVToolNix',
        r'C:\MKVToolNix',
    ]:
        p = os.path.join(d, exe)
        if os.path.exists(p):
            return p
    return tool_name


def _scan_ffmpeg_installs() -> list:
    """Scan for all FFmpeg installations on this system.

    Returns list of dicts: {path, real_path, version, date, label}
    """
    import datetime as _dt

    candidates_raw = []

    # 1. PATH shutil.which
    p = shutil.which('ffmpeg')
    if p:
        candidates_raw.append(p)

    # 2. WinGet Links (symlink)
    winget_link = os.path.expanduser(
        r'~\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe')
    candidates_raw.append(winget_link)

    # 3. WinGet Packages (glob)
    winget_pkgs = os.path.expanduser(
        r'~\AppData\Local\Microsoft\WinGet\Packages')
    if os.path.isdir(winget_pkgs):
        for exe in glob.glob(
                os.path.join(winget_pkgs, 'FFmpeg*', '**', 'ffmpeg.exe'),
                recursive=True):
            candidates_raw.append(exe)

    # 4. Scoop
    for sp in [
        os.path.expanduser(r'~\scoop\apps\ffmpeg\current\bin\ffmpeg.exe'),
        os.path.expanduser(r'~\scoop\shims\ffmpeg.exe'),
        r'C:\ProgramData\scoop\apps\ffmpeg\current\bin\ffmpeg.exe',
    ]:
        candidates_raw.append(sp)

    # 5. Chocolatey
    candidates_raw.append(r'C:\ProgramData\chocolatey\bin\ffmpeg.exe')

    # 6. Common manual installs
    for d in [r'C:\ffmpeg\bin', r'C:\Program Files\ffmpeg\bin',
              r'C:\Program Files (x86)\ffmpeg\bin']:
        candidates_raw.append(os.path.join(d, 'ffmpeg.exe'))

    # 7. App-local
    candidates_raw.append(os.path.join(APP_DIR, 'ffmpeg.exe'))

    seen_real = set()
    results = []

    for raw_path in candidates_raw:
        if not raw_path or not os.path.isfile(raw_path):
            continue
        try:
            real = os.path.realpath(raw_path)
        except Exception:
            real = raw_path
        if real in seen_real:
            continue
        seen_real.add(real)

        # Get version string
        try:
            r = subprocess.run(
                [raw_path, '-version'],
                capture_output=True, text=True, timeout=4,
                startupinfo=get_startupinfo()
            )
            first = (r.stdout or r.stderr or '').split('\n')[0]
            m = re.search(r'version\s+(\S+)', first)
            version = m.group(1) if m else 'unknown'
        except Exception:
            version = 'unknown'

        # Get file date
        try:
            mtime = os.path.getmtime(real)
            date_str = _dt.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
        except Exception:
            date_str = '?'

        results.append({
            'path': raw_path,
            'real_path': real,
            'version': version,
            'date': date_str,
            'label': f"v{version}  [{date_str}]  —  {raw_path}",
        })

    return results


# ============================================================================
# MEDIA FILENAME PARSING — detect series/movie, season/episode, year
# ============================================================================

# Common release-group junk to strip
_JUNK_TOKENS = re.compile(
    r'\b(1080p|2160p|720p|480p|4k|uhd|hdr10\+?|hdr|dolby\s*vision|dv|web-?dl|web-?rip|'
    r'webrip|web|bluray|blu-?ray|bdrip|brrip|hdtv|dvdrip|x264|x265|h\.?264|h\.?265|'
    r'hevc|avc|av1|aac|ac3|eac3|dts(-hd)?|truehd|atmos|flac|opus|10bit|8bit|'
    r'vostfr|multi|vf|vff|vfq|vo|subfr|french|english|truefrench)\b',
    re.IGNORECASE
)


def parse_media_filename(filename):
    """Parse a media filename to detect type, title, season, episode, year.

    Returns dict:
        {kind: 'series'|'movie', title, season, episode, episode_end, year, raw}
    """
    name = os.path.splitext(os.path.basename(filename))[0]
    result = {
        'kind': None, 'title': '', 'season': None, 'episode': None,
        'episode_end': None, 'year': None, 'raw': name,
    }

    # Normalize separators
    work = name.replace('_', ' ').replace('.', ' ')

    # --- Series patterns ---
    # SxxExx(-Exx) / SxxExxExx
    m = re.search(r'[Ss](\d{1,2})[\s._-]*[Ee](\d{1,3})(?:[\s._-]*[Ee](\d{1,3}))?', name)
    if m:
        result['kind'] = 'series'
        result['season'] = int(m.group(1))
        result['episode'] = int(m.group(2))
        if m.group(3):
            result['episode_end'] = int(m.group(3))
        # Title = everything before the SxxExx marker
        title = work[:m.start()].strip(' -._')
        result['title'] = _clean_title(title)
        return result

    # 1x07 style
    m = re.search(r'\b(\d{1,2})x(\d{1,3})\b', name)
    if m:
        result['kind'] = 'series'
        result['season'] = int(m.group(1))
        result['episode'] = int(m.group(2))
        title = work[:m.start()].strip(' -._')
        result['title'] = _clean_title(title)
        return result

    # --- Movie pattern: title (year) ---
    m = re.search(r'\b(19\d{2}|20\d{2})\b', name)
    if m:
        result['kind'] = 'movie'
        result['year'] = int(m.group(1))
        title = work[:m.start()].strip(' -._()[]')
        result['title'] = _clean_title(title)
        return result

    # Fallback: unknown, treat as movie with cleaned title
    result['kind'] = 'movie'
    result['title'] = _clean_title(work)
    return result


def _clean_title(title):
    """Strip release-group junk and normalize a title string."""
    # Remove bracketed groups [xxx] (yyy)
    title = re.sub(r'[\[\(][^\]\)]*[\]\)]', ' ', title)
    # Remove junk tokens
    title = _JUNK_TOKENS.sub(' ', title)
    # Collapse whitespace and trailing dashes
    title = re.sub(r'\s+', ' ', title).strip(' -._')
    # Strip a trailing isolated single letter (broken possessive: "Hero s" → "Hero")
    title = re.sub(r'\s+[a-z]$', '', title)
    return title


# ============================================================================
# VIDEO METADATA DETECTION — resolution, codec, HDR
# ============================================================================

def detect_video_metadata(mkv_path, mkvmerge_path, ffprobe_path):
    """Detect resolution label, codec, and HDR type from a video file.

    Returns dict: {resolution, codec, hdr, width, height}
    """
    meta = {'resolution': '', 'codec': '', 'hdr': '', 'width': 0, 'height': 0}

    # --- mkvmerge -J for codec + dimensions ---
    try:
        res = run_hidden([mkvmerge_path, "-J", mkv_path])
        info = json.loads(res.stdout)
        for t in info.get("tracks", []):
            if t.get("type") == "video":
                props = t.get("properties", {})
                dim = props.get("pixel_dimensions", "")  # "1920x1080"
                if "x" in dim:
                    w, h = dim.split("x")
                    meta['width'] = int(w)
                    meta['height'] = int(h)
                codec_id = props.get("codec_id", "")
                codec_name = t.get("codec", "")
                meta['codec'] = _normalize_codec(codec_id, codec_name)
                break
    except Exception as e:
        logger.debug(f"mkvmerge metadata failed: {e}")

    # --- ffprobe for HDR detection ---
    try:
        cmd = [ffprobe_path, "-v", "error", "-select_streams", "v:0",
               "-show_entries",
               "stream=color_transfer,color_primaries,color_space:stream_side_data=dv_profile",
               "-of", "json", mkv_path]
        out = run_hidden(cmd).stdout
        pdata = json.loads(out)
        streams = pdata.get("streams", [])
        if streams:
            s = streams[0]
            transfer = (s.get("color_transfer") or "").lower()
            # Dolby Vision: side_data dv_profile present
            side = s.get("side_data_list", [])
            has_dv = any("dv_profile" in sd or sd.get("side_data_type", "").lower().startswith("dolby")
                         for sd in side) if isinstance(side, list) else False
            if not has_dv and "dv_profile" in str(pdata):
                has_dv = True
            if has_dv:
                meta['hdr'] = 'Dolby Vision'
            elif transfer in ('smpte2084', 'arib-std-b67'):
                meta['hdr'] = 'HDR10' if transfer == 'smpte2084' else 'HLG'
    except Exception as e:
        logger.debug(f"ffprobe HDR detection failed: {e}")

    # --- Resolution label from height ---
    h = meta['height']
    w = meta['width']
    if h >= 2000 or w >= 3000:
        meta['resolution'] = '2160p'
    elif h >= 1000 or w >= 1800:
        meta['resolution'] = '1080p'
    elif h >= 700 or w >= 1200:
        meta['resolution'] = '720p'
    elif h >= 500:
        meta['resolution'] = '576p'
    elif h > 0:
        meta['resolution'] = '480p'

    return meta


def _normalize_codec(codec_id, codec_name):
    """Map mkv codec id/name to a clean display label."""
    c = (codec_id + " " + codec_name).upper()
    if 'V_AV1' in c or 'AV1' in c:
        return 'AV1'
    if 'HEVC' in c or 'H265' in c or 'V_MPEGH' in c or 'X265' in c:
        return 'x265'
    if 'AVC' in c or 'H264' in c or 'V_MPEG4' in c or 'X264' in c:
        return 'x264'
    if 'VP9' in c:
        return 'VP9'
    if 'MPEG2' in c:
        return 'MPEG2'
    # --- audio ---
    if 'TRUEHD' in c or 'TRUE-HD' in c:
        return 'TrueHD'
    if 'E-AC-3' in c or 'EAC3' in c or 'EC-3' in c:
        return 'EAC3'
    if 'AC-3' in c or 'A_AC3' in c or 'AC3' in c:
        return 'AC3'
    if 'DTS-HD' in c or 'DTSHD' in c:
        return 'DTS-HD'
    if 'DTS' in c:
        return 'DTS'
    if 'AAC' in c:
        return 'AAC'
    if 'FLAC' in c:
        return 'FLAC'
    if 'OPUS' in c:
        return 'Opus'
    if 'VORBIS' in c:
        return 'Vorbis'
    if 'MP3' in c or 'MPEG/L3' in c:
        return 'MP3'
    if 'PCM' in c:
        return 'PCM'
    # --- subtitles ---
    if 'PGS' in c or 'HDMV' in c:
        return 'PGS'
    if 'S_TEXT/ASS' in c or 'SSA' in c or 'ASS' in c:
        return 'ASS'
    if 'S_TEXT/UTF8' in c or 'SRT' in c or 'SUBRIP' in c:
        return 'SRT'
    if 'VOBSUB' in c or 'S_VOBSUB' in c:
        return 'VobSub'
    return codec_name or ''


# ============================================================================
# METADATA PROVIDERS — TVDB v4, TMDB, TVmaze (fallback chain)
# ============================================================================

def _http_get_json(url, headers=None, timeout=12):
    """GET a URL and return parsed JSON, or None on failure."""
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        logger.debug(f"HTTP GET failed [{url}]: {e}")
        return None


def _http_post_json(url, payload, headers=None, timeout=12):
    """POST JSON to a URL and return parsed JSON, or None on failure."""
    try:
        data = json.dumps(payload).encode('utf-8')
        h = {'Content-Type': 'application/json'}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=data, headers=h, method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        logger.debug(f"HTTP POST failed [{url}]: {e}")
        return None


class TVDBProvider:
    """TheTVDB v4 API client. Requires API key. Series + movies."""
    BASE = "https://api4.thetvdb.com/v4"

    def __init__(self, api_key, lang='fra'):
        self.api_key = api_key
        self.lang = lang
        self.token = None

    def _login(self):
        if self.token:
            return True
        data = _http_post_json(f"{self.BASE}/login", {"apikey": self.api_key})
        if data and data.get("status") == "success":
            self.token = data["data"]["token"]
            return True
        return False

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def search_series(self, title):
        """Return list of {id, name, year} for series matching title."""
        if not self._login():
            return []
        q = urllib.parse.quote(title)
        url = f"{self.BASE}/search?query={q}&type=series"
        data = _http_get_json(url, self._headers())
        if not data or "data" not in data:
            return []
        out = []
        for item in data["data"][:8]:
            out.append({
                'id': item.get("tvdb_id") or item.get("id"),
                'name': item.get("translations", {}).get(self.lang) or item.get("name", ""),
                'year': item.get("year", ""),
                'provider': 'TVDB',
            })
        return out

    def get_episode_name(self, series_id, season, episode):
        """Return localized episode name for a series/season/episode."""
        if not self._login():
            return None
        sid = str(series_id).replace("series-", "")
        url = (f"{self.BASE}/series/{sid}/episodes/default/{self.lang}"
               f"?season={season}&episodeNumber={episode}")
        data = _http_get_json(url, self._headers())
        try:
            eps = data["data"]["episodes"]
            for ep in eps:
                if ep.get("seasonNumber") == season and ep.get("number") == episode:
                    return ep.get("name")
        except Exception:
            pass
        # Fallback: extended translations
        return None

    def get_series_name(self, series_id):
        if not self._login():
            return None
        sid = str(series_id).replace("series-", "")
        data = _http_get_json(f"{self.BASE}/series/{sid}/translations/{self.lang}",
                              self._headers())
        try:
            return data["data"]["name"]
        except Exception:
            return None

    def get_episode_meta(self, series_id, season, episode):
        """Return {name, description, still_url, aired, episode_id} for an episode."""
        if not self._login():
            return {}
        sid = str(series_id).replace("series-", "")
        url = (f"{self.BASE}/series/{sid}/episodes/default/{self.lang}"
               f"?season={season}&episodeNumber={episode}")
        data = _http_get_json(url, self._headers())
        try:
            for ep in data["data"]["episodes"]:
                if ep.get("seasonNumber") == season and ep.get("number") == episode:
                    return {
                        'name': ep.get("name", ""),
                        'description': ep.get("overview", ""),
                        'still_url': ep.get("image", ""),
                        'aired': ep.get("aired", ""),
                        'episode_id': ep.get("id"),
                    }
        except Exception:
            pass
        return {}

    def get_series_meta(self, series_id):
        """Return {genres, content_rating, imdb_id, cast} for a series."""
        if not self._login():
            return {}
        sid = str(series_id).replace("series-", "")
        data = _http_get_json(f"{self.BASE}/series/{sid}/extended", self._headers())
        result = {}
        try:
            d = data["data"]
            result['genres'] = [g.get("name", "") for g in d.get("genres", []) if g.get("name")]
            ratings = d.get("contentRatings", [])
            if ratings:
                result['content_rating'] = ratings[0].get("name", "")
            for rid in d.get("remoteIds", []):
                if rid.get("type") == 2 or "imdb" in rid.get("sourceName", "").lower():
                    result['imdb_id'] = rid.get("id", "")
                    break
            # Series-level cast as fallback
            series_cast = []
            for c in d.get("characters", [])[:15]:
                name = c.get("personName", "")
                role = c.get("name", "")
                if name:
                    series_cast.append({'name': name, 'role': role})
            if series_cast:
                result['cast'] = series_cast
        except Exception:
            pass
        return result

    def get_episode_extended(self, episode_id):
        """Return {cast: [{name, role}]} from extended episode data."""
        if not self._login() or not episode_id:
            return {}
        data = _http_get_json(f"{self.BASE}/episodes/{episode_id}/extended", self._headers())
        result = {}
        try:
            d = data["data"]
            cast = []
            for c in d.get("characters", [])[:15]:
                name = c.get("personName", "")
                role = c.get("name", "")
                if name:
                    cast.append({'name': name, 'role': role})
            result['cast'] = cast
        except Exception:
            pass
        return result

    def get_series_poster(self, series_id):
        """Return poster image URL for a series."""
        if not self._login():
            return ""
        sid = str(series_id).replace("series-", "")
        data = _http_get_json(f"{self.BASE}/series/{sid}", self._headers())
        try:
            return data["data"].get("image", "")
        except Exception:
            return ""


class TMDBProvider:
    """TMDB API client. Requires API key. Series + movies."""
    BASE = "https://api.themoviedb.org/3"

    def __init__(self, api_key, lang='fr-FR'):
        self.api_key = api_key
        self.lang = lang

    def search_series(self, title):
        q = urllib.parse.quote(title)
        url = f"{self.BASE}/search/tv?api_key={self.api_key}&language={self.lang}&query={q}"
        data = _http_get_json(url)
        if not data or "results" not in data:
            return []
        out = []
        for item in data["results"][:8]:
            date = item.get("first_air_date", "")
            out.append({
                'id': item.get("id"),
                'name': item.get("name", ""),
                'year': date[:4] if date else "",
                'provider': 'TMDB',
            })
        return out

    def search_movie(self, title, year=None):
        q = urllib.parse.quote(title)
        url = f"{self.BASE}/search/movie?api_key={self.api_key}&language={self.lang}&query={q}"
        if year:
            url += f"&year={year}"
        data = _http_get_json(url)
        if not data or "results" not in data:
            return []
        out = []
        for item in data["results"][:8]:
            date = item.get("release_date", "")
            out.append({
                'id': item.get("id"),
                'name': item.get("title", ""),
                'year': date[:4] if date else "",
                'provider': 'TMDB',
            })
        return out

    def get_episode_name(self, series_id, season, episode):
        url = (f"{self.BASE}/tv/{series_id}/season/{season}/episode/{episode}"
               f"?api_key={self.api_key}&language={self.lang}")
        data = _http_get_json(url)
        if data:
            return data.get("name")
        return None

    def get_episode_meta(self, series_id, season, episode):
        """Return {name, description, still_url, aired} for an episode."""
        url = (f"{self.BASE}/tv/{series_id}/season/{season}/episode/{episode}"
               f"?api_key={self.api_key}&language={self.lang}")
        data = _http_get_json(url)
        if data:
            still = data.get("still_path", "")
            return {
                'name': data.get("name", ""),
                'description': data.get("overview", ""),
                'still_url': f"https://image.tmdb.org/t/p/original{still}" if still else "",
                'aired': data.get("air_date", ""),
            }
        return {}

    def get_episode_cast(self, series_id, season, episode):
        """Return [{name, role}] for an episode's cast + directors/writers in crew.
        Falls back to series-level created_by + studios when episode crew is empty (common for anime).
        """
        url = (f"{self.BASE}/tv/{series_id}/season/{season}/episode/{episode}"
               f"/credits?api_key={self.api_key}")
        data = _http_get_json(url) or {}
        cast = [{'name': a.get('name', ''), 'role': a.get('character', '')}
                for a in data.get('cast', [])[:15] if a.get('name')]
        # Extract directors, writers, producers from episode crew
        directors, writers, producers = [], [], []
        for c in data.get('crew', []):
            dept = c.get('department', '')
            job = c.get('job', '')
            name = c.get('name', '')
            if not name:
                continue
            if dept == 'Directing':
                directors.append(name)
            elif dept == 'Writing':
                writers.append(name)
            elif dept == 'Production' or 'Producer' in job:
                producers.append(name)
        # Fallback: aggregate_credits (all-episode crew) for real producer persons
        studios = []
        if not directors and not producers:
            agg = _http_get_json(f"{self.BASE}/tv/{series_id}/aggregate_credits"
                                 f"?api_key={self.api_key}&language={self.lang}") or {}
            for c in agg.get('crew', []):
                name = c.get('name', '')
                if not name:
                    continue
                jobs = c.get('jobs', [])
                job_names = [j.get('job', '') for j in jobs] if jobs else [c.get('job', '')]
                dept = c.get('department', '')
                if dept == 'Directing' or 'Director' in job_names:
                    directors.append(name)
                elif dept == 'Writing':
                    writers.append(name)
                elif dept == 'Production' or any('Producer' in j for j in job_names):
                    producers.append(name)
            # Studios from created_by / production_companies
            sdata = _http_get_json(f"{self.BASE}/tv/{series_id}"
                                   f"?api_key={self.api_key}&language={self.lang}") or {}
            if not directors:
                for cb in sdata.get('created_by', []):
                    if cb.get('name'):
                        directors.append(cb['name'])
            for comp in sdata.get('production_companies', []):
                if comp.get('name'):
                    studios.append(comp['name'])
        # Dedupe preserving order
        def _dedup(lst):
            seen, out = set(), []
            for x in lst:
                if x not in seen:
                    seen.add(x); out.append(x)
            return out
        directors, writers, producers, studios = (
            _dedup(directors), _dedup(writers), _dedup(producers), _dedup(studios))
        if directors:
            cast.insert(0, {'name': ', '.join(directors[:5]), 'role': '__director__'})
        if writers:
            cast.insert(1, {'name': ', '.join(writers[:5]), 'role': '__writer__'})
        if producers:
            cast.insert(2, {'name': ', '.join(producers[:8]), 'role': '__producer__'})
        if studios:
            cast.insert(3, {'name': ', '.join(studios[:5]), 'role': '__studio__'})
        return cast

    def get_series_meta(self, series_id):
        """Return {genres, content_rating, imdb_id, poster_url} for a series."""
        result = {}
        # Basic info + genres
        url = f"{self.BASE}/tv/{series_id}?api_key={self.api_key}&language={self.lang}"
        data = _http_get_json(url)
        if data:
            result['genres'] = [g['name'] for g in data.get('genres', []) if g.get('name')]
            poster = data.get("poster_path", "")
            if poster:
                result['poster_url'] = f"https://image.tmdb.org/t/p/original{poster}"
        # Content rating
        url2 = f"{self.BASE}/tv/{series_id}/content_ratings?api_key={self.api_key}"
        data2 = _http_get_json(url2)
        if data2:
            for r in data2.get('results', []):
                if r.get('iso_3166_1') in ('FR', 'US'):
                    result['content_rating'] = r.get('rating', '')
                    break
            if not result.get('content_rating') and data2.get('results'):
                result['content_rating'] = data2['results'][0].get('rating', '')
        # IMDB ID
        url3 = f"{self.BASE}/tv/{series_id}/external_ids?api_key={self.api_key}"
        data3 = _http_get_json(url3)
        if data3:
            result['imdb_id'] = data3.get('imdb_id', '')
        return result

    def get_series_poster(self, series_id):
        """Return poster URL for a series."""
        url = f"{self.BASE}/tv/{series_id}?api_key={self.api_key}"
        data = _http_get_json(url)
        if data:
            poster = data.get("poster_path", "")
            if poster:
                return f"https://image.tmdb.org/t/p/original{poster}"
        return ""

    def get_movie_meta(self, movie_id):
        """Return {name, description, poster_url, genres, imdb_id, content_rating} for a movie."""
        url = f"{self.BASE}/movie/{movie_id}?api_key={self.api_key}&language={self.lang}"
        data = _http_get_json(url)
        if not data:
            return {}
        poster = data.get("poster_path", "")
        result = {
            'name': data.get("title", ""),
            'description': data.get("overview", ""),
            'poster_url': f"https://image.tmdb.org/t/p/original{poster}" if poster else "",
            'genres': [g['name'] for g in data.get('genres', []) if g.get('name')],
            'aired': data.get("release_date", ""),
        }
        # IMDB ID
        url2 = f"{self.BASE}/movie/{movie_id}/external_ids?api_key={self.api_key}"
        data2 = _http_get_json(url2)
        if data2:
            result['imdb_id'] = data2.get('imdb_id', '')
        return result


class TVmazeProvider:
    """TVmaze API client. No key required. Series only."""
    BASE = "https://api.tvmaze.com"

    def search_series(self, title):
        q = urllib.parse.quote(title)
        data = _http_get_json(f"{self.BASE}/search/shows?q={q}")
        if not data:
            return []
        out = []
        for item in data[:8]:
            show = item.get("show", {})
            premiered = show.get("premiered", "")
            out.append({
                'id': show.get("id"),
                'name': show.get("name", ""),
                'year': premiered[:4] if premiered else "",
                'provider': 'TVmaze',
            })
        return out

    def get_episode_name(self, series_id, season, episode):
        url = f"{self.BASE}/shows/{series_id}/episodebynumber?season={season}&number={episode}"
        data = _http_get_json(url)
        if data:
            return data.get("name")
        return None

    def get_episode_meta(self, series_id, season, episode):
        """Return {name, description, still_url, aired} for an episode."""
        url = f"{self.BASE}/shows/{series_id}/episodebynumber?season={season}&number={episode}"
        data = _http_get_json(url)
        if data:
            img = data.get("image") or {}
            summary = data.get("summary") or ""
            summary = re.sub(r'<[^>]+>', '', summary).strip()
            return {
                'name': data.get("name", ""),
                'description': summary,
                'still_url': img.get("original", "") if isinstance(img, dict) else "",
                'aired': data.get("airdate", ""),
            }
        return {}

    def get_series_meta(self, series_id):
        """Return {genres, content_rating} for a series."""
        data = _http_get_json(f"{self.BASE}/shows/{series_id}")
        if data:
            rating = data.get('rating', {})
            return {
                'genres': data.get('genres', []),
                'content_rating': str(rating.get('average', '')) if rating.get('average') else '',
            }
        return {}

    def get_episode_cast(self, series_id, season=None, episode=None):
        """Return [{name, role}] for a series' cast."""
        data = _http_get_json(f"{self.BASE}/shows/{series_id}/cast")
        if data:
            return [{'name': c['person']['name'], 'role': c['character']['name']}
                    for c in data[:15]
                    if c.get('person') and c.get('character')]
        return []


class MetadataResolver:
    """Tries providers in order: TVDB → TMDB → TVmaze."""

    def __init__(self, tvdb_key='', tmdb_key='', lang_tvdb='fra', lang_tmdb='fr-FR', include_tvmaze=True):
        self.providers = []
        if tvdb_key:
            self.providers.append(('TVDB', TVDBProvider(tvdb_key, lang_tvdb)))
        if tmdb_key:
            self.providers.append(('TMDB', TMDBProvider(tmdb_key, lang_tmdb)))
        if include_tvmaze:
            self.providers.append(('TVmaze', TVmazeProvider()))

    def search_series(self, title):
        """Return combined search results from first provider that responds."""
        for name, prov in self.providers:
            try:
                results = prov.search_series(title)
                if results:
                    return results
            except Exception as e:
                logger.debug(f"{name} search_series failed: {e}")
        return []

    def search_movie(self, title, year=None):
        for name, prov in self.providers:
            if not hasattr(prov, 'search_movie'):
                continue
            try:
                results = prov.search_movie(title, year)
                if results:
                    return results
            except Exception as e:
                logger.debug(f"{name} search_movie failed: {e}")
        return []

    def resolve_episode(self, provider_name, series_id, season, episode):
        """Get episode name from a specific provider."""
        for name, prov in self.providers:
            if name == provider_name and hasattr(prov, 'get_episode_name'):
                try:
                    return prov.get_episode_name(series_id, season, episode)
                except Exception as e:
                    logger.debug(f"{name} resolve_episode failed: {e}")
        return None

    def resolve_full_episode(self, provider_name, series_id, season, episode):
        """Get rich episode meta: name, description, aired, cast, genres, IMDB, rating, poster."""
        meta = {}
        for name, prov in self.providers:
            if name == provider_name:
                # Episode base info
                if hasattr(prov, 'get_episode_meta'):
                    try:
                        meta = prov.get_episode_meta(series_id, season, episode)
                    except Exception as e:
                        logger.debug(f"{name} get_episode_meta: {e}")
                # Series meta (genres, content rating, IMDB)
                if hasattr(prov, 'get_series_meta'):
                    try:
                        s_meta = prov.get_series_meta(series_id)
                        for k, v in s_meta.items():
                            if v and not meta.get(k):
                                meta[k] = v
                    except Exception as e:
                        logger.debug(f"{name} get_series_meta: {e}")
                # Episode cast (TVDB: via episode_id, others: direct)
                ep_id = meta.get('episode_id')
                if ep_id and hasattr(prov, 'get_episode_extended'):
                    try:
                        ext = prov.get_episode_extended(ep_id)
                        if ext.get('cast'):
                            meta['cast'] = ext['cast']
                    except Exception as e:
                        logger.debug(f"{name} get_episode_extended: {e}")
                elif hasattr(prov, 'get_episode_cast'):
                    try:
                        meta['cast'] = prov.get_episode_cast(series_id, season, episode)
                    except Exception as e:
                        logger.debug(f"{name} get_episode_cast: {e}")
                # Series poster
                if hasattr(prov, 'get_series_poster'):
                    try:
                        meta['poster_url'] = prov.get_series_poster(series_id)
                    except Exception as e:
                        logger.debug(f"{name} get_series_poster: {e}")
                break
        return meta

    def resolve_movie_meta(self, provider_name, movie_id):
        """Get full movie meta {name, description, poster_url} from provider."""
        for name, prov in self.providers:
            if name == provider_name and hasattr(prov, 'get_movie_meta'):
                try:
                    return prov.get_movie_meta(movie_id)
                except Exception as e:
                    logger.debug(f"{name} get_movie_meta failed: {e}")
        return {}


def build_output_filename(parsed, chosen, meta, ext='.mkv'):
    """Build the final filename from parsed info + chosen show + video metadata.

    Series: 'Title - S01E07 - Episode Name.mkv'
    Movie:  'Title (Year) 1080p x265 Dolby Vision.mkv'
    """
    def _sanitize_fname(s):
        # Remove characters illegal in Windows filenames
        return re.sub(r'[<>:"/\\|?*]', '', s).strip()

    if parsed['kind'] == 'series':
        title = _sanitize_fname(chosen.get('name', parsed['title']))
        s = parsed['season'] or 1
        e = parsed['episode'] or 1
        ep_marker = f"S{s:02d}E{e:02d}"
        if parsed.get('episode_end'):
            ep_marker += f"-E{parsed['episode_end']:02d}"
        ep_name = _sanitize_fname(chosen.get('episode_name', ''))
        if ep_name:
            return f"{title} - {ep_marker} - {ep_name}{ext}"
        return f"{title} - {ep_marker}{ext}"
    else:
        title = _sanitize_fname(chosen.get('name', parsed['title']))
        year = chosen.get('year') or parsed.get('year') or ''
        parts = [title]
        if year:
            parts.append(f"({year})")
        # Append metadata tags
        if meta.get('resolution'):
            parts.append(meta['resolution'])
        if meta.get('codec'):
            parts.append(meta['codec'])
        if meta.get('hdr'):
            parts.append(meta['hdr'])
        return " ".join(parts) + ext


# ============================================================================
# TOOLTIP
# ============================================================================

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.id = None
        self.widget.bind("<Enter>", self.schedule_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def schedule_tooltip(self, event):
        self.id = self.widget.after(1200, self.show_tooltip)

    def show_tooltip(self):
        if self.tooltip_window or not self.id:
            return
        try:
            x, y, _, _ = self.widget.bbox("insert")
        except (TypeError, tk.TclError):
            x, y = 0, 0
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left',
                         background='#ffffe0', relief='solid', borderwidth=1, font=("Arial", 10))
        label.pack()

    def hide_tooltip(self, event):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


# ============================================================================
# AUDIO SYNC MIXIN - Shared logic for single & batch sync
# ============================================================================

class AudioSyncMixin:
    """Mixin providing shared audio extraction, correlation, and delay logic."""

    def get_file_duration(self, mkv):
        """Get total duration of a media file via ffprobe (in seconds)."""
        ffprobe = self.settings.get('ffprobe_path', find_ffprobe()) if hasattr(self, 'settings') else find_ffprobe()
        try:
            res = run_hidden([ffprobe, "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nokey=1:noprint_wrappers=1", mkv])
            val = res.stdout.strip()
            if val and re.match(r'^\d+(\.\d+)?$', val):
                return float(val)
        except Exception as e:
            logger.debug(f"Duration probe failed: {e}")
        return 0.0

    def extract_audio_track(self, mkv, ffmpeg_idx, duration, temp_files_list, start_offset=300):
        """Extract audio track to a temporary WAV for analysis.

        Args:
            mkv: path to media file
            ffmpeg_idx: audio stream index
            duration: extraction duration in seconds
            temp_files_list: list to append temp file path to (for cleanup)
            start_offset: seek position in seconds (default 300 = 5min for episodes)
        """
        temp_wav = make_temp_wav()
        temp_files_list.append(temp_wav)

        # Auto-adjust if start_offset + duration exceeds file duration
        file_dur = self.get_file_duration(mkv)
        if file_dur > 0:
            if start_offset >= file_dur:
                # Start would be past end of file -> use beginning
                logger.warning(f"start_offset {start_offset}s >= file duration {file_dur:.1f}s, using 0")
                start_offset = 0
                duration = min(duration, max(int(file_dur) - 1, 1))
            elif start_offset + duration > file_dur:
                # Extraction window overflows -> shrink duration
                new_dur = max(int(file_dur - start_offset) - 1, 1)
                logger.info(f"Adjusting duration from {duration}s to {new_dur}s (file is {file_dur:.1f}s)")
                duration = new_dur

        ffmpeg = self.settings.get('ffmpeg_path', find_ffmpeg()) if hasattr(self, 'settings') else find_ffmpeg()
        cmd = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(start_offset),
            "-i", mkv,
            "-map", f"0:a:{ffmpeg_idx}",
            "-t", str(duration),
            "-ac", "1",
            "-ar", "48000",
            "-f", "wav",
            temp_wav
        ]

        try:
            result = run_hidden(cmd, capture_output=True)
            if result.returncode != 0:
                logger.warning(f"ffmpeg extraction failed: {result.stderr}")
                return None
            if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) < 1000:
                logger.warning(f"Extracted WAV too small or missing (start={start_offset}s, dur={duration}s)")
                return None
            with wave.open(temp_wav, 'rb') as wf:
                raw = wf.readframes(wf.getnframes())
                return np.frombuffer(raw, dtype=np.int16)
        except Exception as e:
            logger.error(f"Audio extraction error: {e}")
            return None

    def calculate_delay(self, ref_data, target_data):
        """Calculate delay between two audio tracks using FFT cross-correlation."""
        # 1. Normalize
        arr_ref = np.array(ref_data, dtype=float) - np.mean(ref_data)
        arr_target = np.array(target_data, dtype=float) - np.mean(target_data)

        # 2. Common length
        min_len = min(len(arr_ref), len(arr_target))
        if min_len == 0:
            return 0
        arr_ref = arr_ref[:min_len]
        arr_target = arr_target[:min_len]

        # 3. FFT cross-correlation
        correlation = signal.correlate(arr_ref, arr_target, mode='full', method='fft')
        lags = signal.correlation_lags(len(arr_ref), len(arr_target), mode='full')

        # 4. Raw peak
        peak_idx = np.argmax(correlation)
        lag = lags[peak_idx]

        # 5. Parabolic interpolation for sub-sample precision
        try:
            if 0 < peak_idx < len(correlation) - 1:
                y1 = correlation[peak_idx - 1]
                y2 = correlation[peak_idx]
                y3 = correlation[peak_idx + 1]
                denom = 2 * (y1 - 2 * y2 + y3)
                if denom != 0:
                    delta = (y1 - y3) / denom
                    lag = lag + delta
        except (IndexError, FloatingPointError) as e:
            logger.debug(f"Parabolic interpolation skipped: {e}")

        # 6. Convert to ms at 48kHz
        delay_ms = (lag / 48000) * 1000
        return int(round(delay_ms))

    def load_mkv_tracks(self, mkv_path, mkvmerge_path):
        """Load track info from an MKV file. Returns list of track dicts."""
        try:
            res = run_hidden([mkvmerge_path, "-J", mkv_path])
            info = json.loads(res.stdout)
            tracks_data = []
            audio_index = 0
            for t in info.get("tracks", []):
                tid = t["id"]
                ttype = t["type"]
                tlang = t.get("properties", {}).get("language", "und")
                tname = t.get("properties", {}).get("track_name", "")
                ffmpeg_idx = -1
                if ttype == "audio":
                    ffmpeg_idx = audio_index
                    audio_index += 1
                if ttype in ["audio", "subtitles"]:
                    tracks_data.append({
                        "id": tid, "type": ttype, "lang": tlang, "name": tname,
                        "ffmpeg_idx": ffmpeg_idx, "delay": 0, "processed": False
                    })
            return tracks_data
        except Exception as e:
            logger.error(f"Failed to load MKV info: {e}")
            return None

    def cleanup_temp(self, temp_files_list):
        """Clean up temporary files."""
        for f in temp_files_list:
            safe_remove(f)
        temp_files_list.clear()

    def apply_mkvpropedit_to_file(self, file, parent_app):
        """Apply mkvpropedit settings to a file."""
        cmd = parent_app.build_mkvpropedit_cmd(file)
        if cmd:
            try:
                process = run_hidden(cmd)
                if process.returncode == 0:
                    return True, "Paramètres mkvpropedit appliqués."
                else:
                    return False, f"Erreur mkvpropedit: {process.stderr}"
            except Exception as e:
                return False, f"Erreur application mkvpropedit: {e}"
        return True, ""


# ============================================================================
# AUDIO SYNC TAB (Single file)
# ============================================================================

class AudioSyncTab(ttk.Frame, AudioSyncMixin):
    def __init__(self, notebook, settings, parent_app):
        super().__init__(notebook)
        self.settings = settings
        self.parent_app = parent_app
        self.pack(fill='both', expand=True)
        self.temp_files = []
        self.tracks_data = []

        main_frame = tk.Frame(self)
        main_frame.pack(padx=10, pady=10, fill='both', expand=True)

        if not HAS_SCIPY:
            tk.Label(main_frame, text=T('warn_no_scipy'), fg="red", font=("Arial", 12, "bold")).pack(pady=20)
            tk.Label(main_frame, text=T('warn_install_scipy'), fg="red").pack()
            return

        # ZONE 1: INPUT
        input_frame = tk.LabelFrame(main_frame, text=T('lbl_select_mkv'), font=("Arial", 9, "bold"))
        input_frame.pack(fill='x', pady=5, ipady=5)

        self.mkv_entry = tk.Entry(input_frame)
        self.mkv_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=5)
        tk.Button(input_frame, text=T('btn_open_mkv'), command=self.load_mkv_info, bg='#e1e1e1').pack(side=tk.LEFT, padx=5)

        # DnD support for mkv entry
        if TkinterDnD is not None:
            try:
                self.mkv_entry.drop_target_register(DND_FILES)
                self.mkv_entry.dnd_bind('<<Drop>>', self._drop_mkv_entry)
            except Exception:
                pass

        # ZONE 2: SETTINGS
        top_panel = tk.Frame(main_frame)
        top_panel.pack(fill='x', pady=5)
        tk.Label(top_panel, text=T('lbl_ref_lang')).pack(side=tk.LEFT)
        self.ref_lang_var = tk.StringVar(value="jpn")
        tk.Entry(top_panel, textvariable=self.ref_lang_var, width=5).pack(side=tk.LEFT, padx=5)
        tk.Label(top_panel, text=T('lbl_duration')).pack(side=tk.LEFT, padx=(10, 0))
        self.duration_var = tk.StringVar(value=settings.get('audio_sync_duration', "120"))
        tk.Entry(top_panel, textvariable=self.duration_var, width=5).pack(side=tk.LEFT, padx=5)
        tk.Label(top_panel, text=T('lbl_start_offset')).pack(side=tk.LEFT, padx=(10, 0))
        self.start_offset_var = tk.StringVar(value=settings.get('audio_sync_start', "300"))
        tk.Entry(top_panel, textvariable=self.start_offset_var, width=5).pack(side=tk.LEFT, padx=5)
        tk.Label(top_panel, text=T('lbl_start_offset_hint')).pack(side=tk.LEFT, padx=2)

        # ZONE 3: TRACKS TABLE
        tree_frame = tk.Frame(main_frame)
        tree_frame.pack(fill='both', expand=True, pady=5)
        columns = ("ID", "Type", "Lang", "Nom", "Status", "Delay Calc.")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=8)
        self.tree.heading("ID", text="ID"); self.tree.column("ID", width=40, anchor='center')
        self.tree.heading("Type", text="Type"); self.tree.column("Type", width=60, anchor='center')
        self.tree.heading("Lang", text=T('col_lang')); self.tree.column("Lang", width=60, anchor='center')
        self.tree.heading("Nom", text=T('col_name')); self.tree.column("Nom", width=250)
        self.tree.heading("Status", text=T('col_status')); self.tree.column("Status", width=120, anchor='center')
        self.tree.heading("Delay Calc.", text=T('col_delay')); self.tree.column("Delay Calc.", width=100, anchor='center')
        self.tree.pack(side=tk.LEFT, fill='both', expand=True)
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        sb.pack(side=tk.RIGHT, fill='y')
        self.tree.configure(yscrollcommand=sb.set)

        # ZONE 4: ACTIONS
        action_frame = tk.Frame(main_frame)
        action_frame.pack(fill='x', pady=10)
        self.apply_subs_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(action_frame, text=T('chk_apply_subs'), variable=self.apply_subs_var).pack(side=tk.TOP, pady=5)
        self.apply_props_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(action_frame, text=T('chk_apply_props'), variable=self.apply_props_var).pack(side=tk.TOP, pady=5)

        btn_box = tk.Frame(action_frame)
        btn_box.pack(fill='x', pady=5)
        self.analyze_btn = tk.Button(btn_box, text=T('btn_analyze'), command=self.start_analysis, bg='#0066ff', fg='white', font=("Arial", 11, "bold"), state='disabled')
        self.analyze_btn.pack(side=tk.LEFT, padx=10, fill='x', expand=True)
        self.apply_btn = tk.Button(btn_box, text=T('btn_apply_delays'), command=self.apply_delays, bg='#008000', fg='white', font=("Arial", 11, "bold"), state='disabled')
        self.apply_btn.pack(side=tk.LEFT, padx=10, fill='x', expand=True)
        self.log_lbl = tk.Label(main_frame, text=T('lbl_waiting'), fg="gray", font=("Arial", 10, "italic"))
        self.log_lbl.pack(side=tk.BOTTOM, pady=5)

    def _drop_mkv_entry(self, event):
        """Handle drag-and-drop onto the MKV entry."""
        files = self.mkv_entry.tk.splitlist(event.data)
        if files:
            f = files[0].strip('{}')
            if f.lower().endswith('.mkv'):
                self._load_mkv_path(f)

    def _load_mkv_path(self, f):
        """Load a MKV file path into the entry and refresh track info (DnD + shared helper)."""
        self.mkv_entry.delete(0, tk.END)
        self.mkv_entry.insert(0, f)
        self.tree.delete(*self.tree.get_children())
        self.tracks_data = []
        self.analyze_btn.config(state='normal')
        self.apply_btn.config(state='disabled')
        self.log_lbl.config(text=T('lbl_file_loaded'))
        mkvmerge = self.parent_app.mkvmerge_path_entry.get() if hasattr(self, 'parent_app') and hasattr(self.parent_app, 'mkvmerge_path_entry') else self.settings.get('mkvmerge_path', 'mkvmerge')
        tracks = self.load_mkv_tracks(f, mkvmerge)
        if tracks:
            self.tracks_data = tracks
            for t in tracks:
                self.tree.insert("", "end", iid=t["id"],
                                 values=(t["id"], t["type"], t["lang"], t["name"], "En attente", "-"))
        else:
            messagebox.showerror("Erreur", "Impossible de lire le fichier.")

    def load_mkv_info(self):
        f = filedialog.askopenfilename(filetypes=[("MKV Files", "*.mkv")])
        if not f:
            return
        self.mkv_entry.delete(0, tk.END)
        self.mkv_entry.insert(0, f)
        self.tree.delete(*self.tree.get_children())
        self.tracks_data = []
        self.analyze_btn.config(state='normal')
        self.apply_btn.config(state='disabled')
        self.log_lbl.config(text="Fichier chargé. Cliquez sur Analyse.")

        mkvmerge = self.parent_app.mkvmerge_path_entry.get() if hasattr(self, 'parent_app') and hasattr(self.parent_app, 'mkvmerge_path_entry') else self.settings.get('mkvmerge_path', 'mkvmerge')
        tracks = self.load_mkv_tracks(f, mkvmerge)
        if tracks:
            self.tracks_data = tracks
            for t in tracks:
                self.tree.insert("", "end", iid=t["id"],
                                 values=(t["id"], t["type"], t["lang"], t["name"], "En attente", "-"))
        else:
            messagebox.showerror("Erreur", "Impossible de lire le fichier.")

    def start_analysis(self):
        ref_lang = self.ref_lang_var.get()
        ref_track = None
        for t in self.tracks_data:
            if t["type"] == "audio" and t["lang"] == ref_lang:
                ref_track = t
                break
        if not ref_track:
            for t in self.tracks_data:
                if t["type"] == "audio":
                    ref_track = t
                    messagebox.showinfo("Info", f"Pas de piste '{ref_lang}'. Utilisation piste {t['id']}.")
                    break
        if not ref_track:
            messagebox.showerror("Erreur", "Aucune piste audio.")
            return

        self.after(0, lambda: self.tree.set(ref_track["id"], "Status", "REFERENCE"))
        self.after(0, lambda: self.tree.item(ref_track["id"], tags=('ref',)))
        threading.Thread(target=self.process_analysis, args=(ref_track,), daemon=True).start()

    def process_analysis(self, ref_track):
        self.after(0, lambda: self.analyze_btn.config(state='disabled'))
        mkv_path = self.mkv_entry.get()
        try:
            duration = int(self.duration_var.get())
        except (ValueError, AttributeError):
            duration = 120
        try:
            start_offset = int(self.start_offset_var.get())
        except (ValueError, AttributeError):
            start_offset = 300

        try:
            self._update_log(f"Extraction REF (Track {ref_track['id']})...")
            ref_data = self.extract_audio_track(mkv_path, ref_track["ffmpeg_idx"], duration, self.temp_files, start_offset)
            if ref_data is None:
                raise Exception("Echec extraction Ref")

            for t in self.tracks_data:
                if t["type"] == "audio" and t["id"] != ref_track["id"]:
                    self._update_log(f"Comparaison Track {t['id']} ({t['lang']})...")
                    self.after(0, lambda tid=t["id"]: self.tree.set(tid, "Status", "Extraction..."))
                    target_data = self.extract_audio_track(mkv_path, t["ffmpeg_idx"], duration, self.temp_files, start_offset)
                    if target_data is not None:
                        self.after(0, lambda tid=t["id"]: self.tree.set(tid, "Status", "Calcul..."))
                        delay = self.calculate_delay(ref_data, target_data)
                        t["delay"] = delay
                        t["processed"] = True
                        sign = "+" if delay > 0 else ""
                        self.after(0, lambda tid=t["id"], d=f"{sign}{delay} ms": self.tree.set(tid, "Delay Calc.", d))
                        self.after(0, lambda tid=t["id"]: self.tree.set(tid, "Status", "OK"))
                    else:
                        self.after(0, lambda tid=t["id"]: self.tree.set(tid, "Status", "Erreur Extr."))

            if self.apply_subs_var.get():
                self._update_log("Synchronisation des sous-titres...")
                lang_delays = {}
                for t in self.tracks_data:
                    if t["type"] == "audio" and t["processed"]:
                        lang_delays[t["lang"]] = t["delay"]
                for t in self.tracks_data:
                    if t["type"] == "subtitles" and t["lang"] in lang_delays:
                        delay = lang_delays[t["lang"]]
                        t["delay"] = delay
                        t["processed"] = True
                        sign = "+" if delay > 0 else ""
                        self.after(0, lambda tid=t["id"], d=f"({sign}{delay} ms)": self.tree.set(tid, "Delay Calc.", d))
                        self.after(0, lambda tid=t["id"]: self.tree.set(tid, "Status", "Via Audio"))

            self._update_log("Analyse terminée. Vérifiez et appliquez.")
            self.after(0, lambda: self.apply_btn.config(state='normal'))
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            self.after(0, lambda: messagebox.showerror("Erreur Process", str(e)))
            self.after(0, lambda: self.analyze_btn.config(state='normal'))
        finally:
            self.cleanup_temp(self.temp_files)

    def apply_delays(self):
        mkv = self.mkv_entry.get().strip('"')
        mkvmerge = self.parent_app.mkvmerge_path_entry.get() if hasattr(self, 'parent_app') and hasattr(self.parent_app, 'mkvmerge_path_entry') else self.settings.get('mkvmerge_path', 'mkvmerge')
        base, ext = os.path.splitext(mkv)
        output_file = f"{base}_SYNC{ext}"
        cmd = [mkvmerge, "-o", output_file]

        count = 0
        sync_flags = []
        for t in self.tracks_data:
            if t["processed"] and t["delay"] != 0:
                sync_flags += ["--sync", f"{t['id']}:{t['delay']}"]
                count += 1

        if count == 0:
            # No delays to apply — but still run mkvpropedit on original if requested
            if self.apply_props_var.get():
                self._update_log("Aucun délai. Application des paramètres mkvpropedit sur le fichier original.")
                success, msg = self.apply_mkvpropedit_to_file(mkv, self.parent_app)
                self._update_log(msg)
            else:
                messagebox.showinfo("Info", "Aucun délai à appliquer.")
            return

        cmd += sync_flags
        cmd += [mkv]

        try:
            self._update_log(f"Remuxing en cours ({count} pistes)... Patientez.")
            self.apply_btn.config(state='disabled')
            process = run_hidden(cmd)

            if process.returncode == 0:
                messagebox.showinfo("Succès", f"Nouveau fichier créé :\n{os.path.basename(output_file)}\n\nLes délais ont été appliqués définitivement.")
                self._update_log("Terminé. Fichier _SYNC créé.")
                if self.apply_props_var.get():
                    success, msg = self.apply_mkvpropedit_to_file(output_file, self.parent_app)
                    self._update_log(msg)
            else:
                messagebox.showerror("Erreur mkvmerge", f"Code: {process.returncode}\n{process.stderr}")
                self._update_log("Erreur lors du remuxing.")
        except Exception as e:
            messagebox.showerror("Erreur Critique", f"Echec : {e}")
        finally:
            self.apply_btn.config(state='normal')

    def _update_log(self, txt):
        self.after(0, lambda: self.log_lbl.config(text=txt))


# ============================================================================
# AUDIO SYNC BATCH TAB
# ============================================================================

class AudioSyncBatchTab(ttk.Frame, AudioSyncMixin):
    def __init__(self, notebook, settings, parent_app):
        super().__init__(notebook)
        self.settings = settings
        self.parent_app = parent_app
        self.pack(fill='both', expand=True)
        self.temp_files = []

        main_frame = tk.Frame(self)
        main_frame.pack(padx=10, pady=10, fill='both', expand=True)

        if not HAS_SCIPY:
            tk.Label(main_frame, text=T('warn_no_scipy'), fg="red", font=("Arial", 12, "bold")).pack(pady=20)
            tk.Label(main_frame, text=T('warn_install_scipy'), fg="red").pack()
            return

        # ZONE 1: File list
        listbox_frame = tk.Frame(main_frame)
        listbox_frame.pack(fill='both', expand=True, pady=5)

        self.file_list = tk.Listbox(listbox_frame, selectmode=tk.MULTIPLE, height=10)
        self.file_list.pack(side="left", fill='both', expand=True)

        sb = ttk.Scrollbar(listbox_frame, orient="vertical", command=self.file_list.yview)
        sb.pack(side="right", fill="y")
        self.file_list.configure(yscrollcommand=sb.set)

        if TkinterDnD is not None:
            try:

                self.file_list.drop_target_register(DND_FILES)

                self.file_list.dnd_bind('<<Drop>>', self.drop_files)

            except Exception:

                logger.warning("tkdnd not available for self.file_list")

        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=5)
        tk.Button(btn_frame, text=T('btn_add_files'), command=self.add_files, bg='#ADD8E6', fg='#000000').pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text=T('btn_add_folder'), command=self.add_folder, bg='#800080', fg='white').pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text=T('btn_remove'), command=self.remove_selected, bg='#FF4500', fg='white').pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text=T('btn_clear'), command=self.clear_files, bg='#FF0000', fg='white').pack(side=tk.LEFT, padx=5)

        # ZONE 2: Settings
        settings_frame = tk.Frame(main_frame)
        settings_frame.pack(fill='x', pady=5)

        tk.Label(settings_frame, text=T('lbl_ref_lang')).pack(side=tk.LEFT)
        self.ref_lang_var = tk.StringVar(value="jpn")
        tk.Entry(settings_frame, textvariable=self.ref_lang_var, width=5).pack(side=tk.LEFT, padx=5)

        tk.Label(settings_frame, text=T('lbl_duration')).pack(side=tk.LEFT, padx=(10, 0))
        self.duration_var = tk.StringVar(value=settings.get('audio_sync_duration', "120"))
        tk.Entry(settings_frame, textvariable=self.duration_var, width=5).pack(side=tk.LEFT, padx=5)
        tk.Label(settings_frame, text=T('lbl_batch_start')).pack(side=tk.LEFT, padx=(10, 0))
        self.start_offset_var = tk.StringVar(value=settings.get('audio_sync_start', "300"))
        tk.Entry(settings_frame, textvariable=self.start_offset_var, width=5).pack(side=tk.LEFT, padx=5)
        tk.Label(settings_frame, text=T('lbl_start_hint_short')).pack(side=tk.LEFT, padx=2)

        self.apply_subs_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text=T('chk_apply_subs_short'), variable=self.apply_subs_var).pack(side=tk.LEFT, padx=10)

        self.apply_props_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text=T('chk_apply_props'), variable=self.apply_props_var).pack(side=tk.LEFT, padx=10)

        # ZONE 3: Actions
        action_frame = tk.Frame(main_frame)
        action_frame.pack(fill='x', pady=10)

        self.start_btn = tk.Button(action_frame, text=T('btn_start_batch'), command=self.start_batch, bg='#0066ff', fg='white', font=("Arial", 11, "bold"))
        self.start_btn.pack(side=tk.LEFT, padx=10, fill='x', expand=True)

        self.progress = ttk.Progressbar(main_frame, orient='horizontal', length=400, mode='determinate')
        self.progress.pack(pady=10)

        self.log_text = scrolledtext.ScrolledText(main_frame, height=10)
        self.log_text.pack(fill='both', expand=True, pady=5)

    def drop_files(self, event):
        files = self.winfo_toplevel().tk.splitlist(event.data)
        for file in files:
            if file.lower().endswith('.mkv'):
                self.file_list.insert(tk.END, file)

    def add_files(self):
        files = filedialog.askopenfilenames(filetypes=[("MKV Files", "*.mkv")])
        for f in files:
            self.file_list.insert(tk.END, f)

    def add_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            for f in glob.glob(os.path.join(folder, "**/*.mkv"), recursive=True):
                self.file_list.insert(tk.END, f)

    def remove_selected(self):
        for i in self.file_list.curselection()[::-1]:
            self.file_list.delete(i)

    def clear_files(self):
        self.file_list.delete(0, tk.END)

    def start_batch(self):
        files = list(self.file_list.get(0, tk.END))
        if not files:
            messagebox.showwarning("Avertissement", "Aucun fichier ajouté !")
            return
        self.start_btn.config(state='disabled')
        self.progress['maximum'] = len(files)
        self.progress['value'] = 0
        self.log_text.delete("1.0", tk.END)
        threading.Thread(target=self.process_batch, args=(files,), daemon=True).start()

    def process_batch(self, files):
        ref_lang = self.ref_lang_var.get()
        duration = int(self.duration_var.get())
        try:
            start_offset = int(self.start_offset_var.get())
        except (ValueError, AttributeError):
            start_offset = 300
        apply_subs = self.apply_subs_var.get()
        apply_props = self.apply_props_var.get()
        mkvmerge = self.parent_app.mkvmerge_path_entry.get() if hasattr(self, 'parent_app') and hasattr(self.parent_app, 'mkvmerge_path_entry') else self.settings.get('mkvmerge_path', 'mkvmerge')
        start_time = time.time()
        processed = 0

        for idx, mkv_path in enumerate(files):
            self._log(f"Traitement de {os.path.basename(mkv_path)} ({idx + 1}/{len(files)})...")
            try:
                tracks_data = self.load_mkv_tracks(mkv_path, mkvmerge)
                if not tracks_data:
                    self._log(f"Erreur chargement info pour {os.path.basename(mkv_path)}")
                    continue

                ref_track = next((t for t in tracks_data if t["type"] == "audio" and t["lang"] == ref_lang), None)
                if not ref_track:
                    ref_track = next((t for t in tracks_data if t["type"] == "audio"), None)
                    if ref_track:
                        self._log(f"Pas de piste '{ref_lang}'. Utilisation piste {ref_track['id']}.")

                if not ref_track:
                    self._log(f"Aucune piste audio pour {os.path.basename(mkv_path)}.")
                    continue

                ref_data = self.extract_audio_track(mkv_path, ref_track["ffmpeg_idx"], duration, self.temp_files, start_offset)
                if ref_data is None:
                    self._log(f"Echec extraction ref pour {os.path.basename(mkv_path)}")
                    continue

                for t in tracks_data:
                    if t["type"] == "audio" and t["id"] != ref_track["id"]:
                        self._log(f"Comparaison Track {t['id']} ({t['lang']})...")
                        target_data = self.extract_audio_track(mkv_path, t["ffmpeg_idx"], duration, self.temp_files, start_offset)
                        if target_data is not None:
                            delay = self.calculate_delay(ref_data, target_data)
                            t["delay"] = delay
                            t["processed"] = True
                        else:
                            self._log(f"Erreur extraction piste {t['id']}")

                if apply_subs:
                    lang_delays = {t["lang"]: t["delay"] for t in tracks_data if t["type"] == "audio" and t.get("processed")}
                    for t in tracks_data:
                        if t["type"] == "subtitles" and t["lang"] in lang_delays:
                            t["delay"] = lang_delays[t["lang"]]
                            t["processed"] = True

                # Log delays
                for t in tracks_data:
                    if t.get("processed") and t["delay"] != 0:
                        sign = "+" if t["delay"] > 0 else ""
                        self._log(f" - {t['type'].capitalize()} Track {t['id']} ({t['lang']}): {sign}{t['delay']} ms")

                has_delays = any(t.get("processed") and t["delay"] != 0 for t in tracks_data)
                if has_delays:
                    self._apply_delays_batch(mkv_path, tracks_data, mkvmerge)
                    if apply_props:
                        base, ext = os.path.splitext(mkv_path)
                        output_file = f"{base}_SYNC{ext}"
                        if os.path.exists(output_file):
                            success, msg = self.apply_mkvpropedit_to_file(output_file, self.parent_app)
                            if msg:
                                self._log(msg)
                        else:
                            self._log(f"⚠️ Fichier SYNC introuvable pour mkvpropedit: {os.path.basename(output_file)}")
                else:
                    self._log("Aucun délai à appliquer.")
                    if apply_props:
                        self._log("Application des paramètres mkvpropedit sur le fichier original.")
                        success, msg = self.apply_mkvpropedit_to_file(mkv_path, self.parent_app)
                        if msg:
                            self._log(msg)

                self._log(f"Terminé pour {os.path.basename(mkv_path)}.")

            except Exception as e:
                logger.error(f"Batch sync error: {e}")
                self._log(f"Erreur pour {os.path.basename(mkv_path)}: {str(e)}")

            self.cleanup_temp(self.temp_files)
            processed += 1
            self.after(0, lambda v=processed: self.progress.configure(value=v))

            # ETA
            elapsed = time.time() - start_time
            if processed > 0:
                avg = elapsed / processed
                remaining = len(files) - processed
                eta = avg * remaining
                self._log(f"ETA: {int(eta // 60)}m {int(eta % 60)}s")

        self._log("Batch terminé.")
        self.after(0, lambda: self.start_btn.config(state='normal'))
        threading.Thread(target=notify_toast, args=(T('notif_sync_done'), T('notif_sync_body')), daemon=True).start()

    def _apply_delays_batch(self, mkv, tracks_data, mkvmerge):
        base, ext = os.path.splitext(mkv)
        output_file = f"{base}_SYNC{ext}"
        cmd = [mkvmerge, "-o", output_file]
        sync_flags = []
        for t in tracks_data:
            if t.get("processed") and t["delay"] != 0:
                sync_flags += ["--sync", f"{t['id']}:{t['delay']}"]
        if not sync_flags:
            self._log("Aucun délai à appliquer.")
            return
        cmd += sync_flags + [mkv]
        try:
            process = run_hidden(cmd)
            if process.returncode == 0:
                self._log(f"Fichier _SYNC créé pour {os.path.basename(mkv)}.")
            else:
                self._log(f"Erreur mkvmerge: {process.stderr}")
        except Exception as e:
            self._log(f"Erreur critique: {e}")

    def _log(self, txt):
        self.after(0, lambda: self._insert_log(txt))

    def _insert_log(self, txt):
        self.log_text.insert(tk.END, txt + "\n")
        self.log_text.see(tk.END)


# ============================================================================
# FRAME CHECK BATCH TAB
# ============================================================================

class FrameCheckBatchTab(ttk.Frame):
    def __init__(self, notebook, settings):
        super().__init__(notebook)
        self.settings = settings
        self.pack(fill='both', expand=True)

        main_frame = tk.Frame(self)
        main_frame.pack(padx=10, pady=10, fill='both', expand=True)

        # Original files
        ori_frame = tk.LabelFrame(main_frame, text=T('lbl_ori_files'))
        ori_frame.pack(fill='x', pady=5)

        self.ori_list = tk.Listbox(ori_frame, selectmode=tk.MULTIPLE, height=5)
        self.ori_list.pack(side="left", fill='both', expand=True)
        sb_ori = ttk.Scrollbar(ori_frame, orient="vertical", command=self.ori_list.yview)
        sb_ori.pack(side="right", fill="y")
        self.ori_list.configure(yscrollcommand=sb_ori.set)

        if TkinterDnD is not None:
            try:

                self.ori_list.drop_target_register(DND_FILES)

                self.ori_list.dnd_bind('<<Drop>>', self.drop_ori_files)

            except Exception:

                logger.warning("tkdnd not available for self.ori_list")

        btn_ori_frame = tk.Frame(ori_frame)
        btn_ori_frame.pack(side="bottom", fill='x')
        tk.Button(btn_ori_frame, text=T('btn_add_ori'), command=self.add_ori_files).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_ori_frame, text=T('btn_add_ori_folder'), command=self.add_ori_folder).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_ori_frame, text=T('btn_clear_ori'), command=self.clear_ori).pack(side=tk.LEFT, padx=5)

        # Encoded files
        enc_frame = tk.LabelFrame(main_frame, text=T('lbl_enc_files'))
        enc_frame.pack(fill='x', pady=5)

        self.enc_list = tk.Listbox(enc_frame, selectmode=tk.MULTIPLE, height=5)
        self.enc_list.pack(side="left", fill='both', expand=True)
        sb_enc = ttk.Scrollbar(enc_frame, orient="vertical", command=self.enc_list.yview)
        sb_enc.pack(side="right", fill="y")
        self.enc_list.configure(yscrollcommand=sb_enc.set)

        if TkinterDnD is not None:
            try:

                self.enc_list.drop_target_register(DND_FILES)

                self.enc_list.dnd_bind('<<Drop>>', self.drop_enc_files)

            except Exception:

                logger.warning("tkdnd not available for self.enc_list")

        btn_enc_frame = tk.Frame(enc_frame)
        btn_enc_frame.pack(side="bottom", fill='x')
        tk.Button(btn_enc_frame, text=T('btn_add_enc'), command=self.add_enc_files).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_enc_frame, text=T('btn_add_enc_folder'), command=self.add_enc_folder).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_enc_frame, text=T('btn_clear_enc'), command=self.clear_enc).pack(side=tk.LEFT, padx=5)

        # Tolerance setting
        tol_frame = tk.Frame(main_frame)
        tol_frame.pack(fill='x', pady=5)
        tk.Label(tol_frame, text=T('lbl_tolerance')).pack(side=tk.LEFT)
        self.tolerance_var = tk.StringVar(value="1.0")
        tk.Entry(tol_frame, textvariable=self.tolerance_var, width=5).pack(side=tk.LEFT, padx=5)
        ToolTip(tk.Label(tol_frame, text="ℹ️"), "Différence de durée maximale tolérée entre original et encodé")

        # Actions
        action_frame = tk.Frame(main_frame)
        action_frame.pack(fill='x', pady=10)
        self.start_btn = tk.Button(action_frame, text=T('btn_verify'), command=self.start_check, bg='#0066ff', fg='white', font=("Arial", 11, "bold"))
        self.start_btn.pack(side=tk.LEFT, padx=10, fill='x', expand=True)

        self.progress = ttk.Progressbar(main_frame, orient='horizontal', length=400, mode='determinate')
        self.progress.pack(pady=10)

        self.log_text = scrolledtext.ScrolledText(main_frame, height=10)
        self.log_text.pack(fill='both', expand=True, pady=5)

    def drop_ori_files(self, event):
        for f in self.winfo_toplevel().tk.splitlist(event.data):
            if f.lower().endswith('.mkv'):
                self.ori_list.insert(tk.END, f)

    def drop_enc_files(self, event):
        for f in self.winfo_toplevel().tk.splitlist(event.data):
            if f.lower().endswith('.mkv'):
                self.enc_list.insert(tk.END, f)

    def add_ori_files(self):
        for f in filedialog.askopenfilenames(filetypes=[("MKV Files", "*.mkv")]):
            self.ori_list.insert(tk.END, f)

    def add_ori_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            for f in glob.glob(os.path.join(folder, "**/*.mkv"), recursive=True):
                self.ori_list.insert(tk.END, f)

    def clear_ori(self):
        self.ori_list.delete(0, tk.END)

    def add_enc_files(self):
        for f in filedialog.askopenfilenames(filetypes=[("MKV Files", "*.mkv")]):
            self.enc_list.insert(tk.END, f)

    def add_enc_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            for f in glob.glob(os.path.join(folder, "**/*.mkv"), recursive=True):
                self.enc_list.insert(tk.END, f)

    def clear_enc(self):
        self.enc_list.delete(0, tk.END)

    def _log(self, text):
        self.after(0, lambda: self._insert_log(text))

    def _insert_log(self, text):
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)

    def start_check(self):
        ori_files = list(self.ori_list.get(0, tk.END))
        enc_files = list(self.enc_list.get(0, tk.END))
        if not ori_files or not enc_files:
            messagebox.showwarning("Avertissement", "Ajoutez des fichiers originaux et encodés !")
            return
        self.start_btn.config(state='disabled')
        self.progress['maximum'] = len(ori_files)
        self.progress['value'] = 0
        self.log_text.delete("1.0", tk.END)
        threading.Thread(target=self.process_check, args=(ori_files, enc_files), daemon=True).start()

    def process_check(self, ori_files, enc_files):
        processed = 0
        start_time = time.time()
        tolerance = float(self.tolerance_var.get())

        self._log("Démarrage de la vérification...")

        enc_map = {}
        for f in enc_files:
            name_no_ext = os.path.splitext(os.path.basename(f))[0]
            enc_map[name_no_ext] = f

        for ori in ori_files:
            base_ori = os.path.basename(ori)
            name_ori_no_ext = os.path.splitext(base_ori)[0]

            match_file = enc_map.get(name_ori_no_ext)
            if not match_file:
                for enc_name, enc_path in enc_map.items():
                    if name_ori_no_ext in enc_name:
                        match_file = enc_path
                        break

            if not match_file:
                self._log(f"❌ Pas de correspondance trouvée pour : {base_ori}")
                continue

            self._log(f"Comparaison : {base_ori} <-> {os.path.basename(match_file)}")

            ori_frames = self._get_frame_count(ori)
            enc_frames = self._get_frame_count(match_file)
            ori_duration = self._get_duration(ori)
            enc_duration = self._get_duration(match_file)

            if ori_frames is None or enc_frames is None:
                self._log(f"   ⚠️ Impossible de lire les frames. Vérifiez ffprobe.")
            else:
                diff = abs(ori_frames - enc_frames)
                status = "✅ OK" if diff == 0 else f"❌ DIFF ({diff} frames)"
                self._log(f"   Frames : {status} (Ori: {ori_frames} | Enc: {enc_frames})")

            if ori_duration is not None and enc_duration is not None:
                dur_diff = abs(ori_duration - enc_duration)
                if dur_diff > tolerance:
                    self._log(f"   ⚠️ Durée différente ! (Diff: {dur_diff:.2f}s)")

            self._log("-" * 30)
            processed += 1
            self.after(0, lambda v=processed: self.progress.configure(value=v))

        self._log("Vérification terminée.")
        self.after(0, lambda: self.start_btn.config(state='normal'))

    def _get_frame_count(self, file_path):
        cmd = [
            self.settings.get('ffprobe_path', find_ffprobe()), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=nb_frames",
            "-of", "default=nokey=1:noprint_wrappers=1", file_path
        ]
        try:
            output = run_hidden(cmd).stdout.strip()
            if output.isdigit():
                return int(output)
        except Exception as e:
            logger.debug(f"nb_frames read failed: {e}")

        try:
            fps = self._get_frame_rate(file_path)
            dur = self._get_duration(file_path)
            if fps and dur:
                return int(dur * fps)
        except Exception as e:
            logger.debug(f"Frame count fallback failed: {e}")
        return None

    def _get_frame_rate(self, file_path):
        cmd = [
            self.settings.get('ffprobe_path', find_ffprobe()), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=nokey=1:noprint_wrappers=1", file_path
        ]
        try:
            output = run_hidden(cmd).stdout.strip()
            if '/' in output:
                num, den = map(int, output.split('/'))
                if den != 0:
                    return num / den
            elif output.replace('.', '', 1).isdigit():
                return float(output)
        except Exception as e:
            logger.debug(f"Frame rate read failed: {e}")
        return None

    def _get_duration(self, file_path):
        cmd = [
            self.settings.get('ffprobe_path', find_ffprobe()), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "format=duration",
            "-of", "default=nokey=1:noprint_wrappers=1", file_path
        ]
        try:
            output = run_hidden(cmd).stdout.strip()
            if re.match(r'^\d+(\.\d+)?$', output):
                return float(output)
        except Exception as e:
            logger.debug(f"Duration read failed: {e}")
        return None


# ============================================================================
# FRAME EXTRACT TAB
# ============================================================================

class FrameExtractTab(ttk.Frame):
    def __init__(self, notebook, settings):
        super().__init__(notebook)
        self.settings = settings
        self.pack(fill='both', expand=True)
        self.stop_event = threading.Event()

        main_frame = tk.Frame(self)
        main_frame.pack(padx=10, pady=10, fill='both', expand=True)

        # ZONE 1: FILE SELECT
        input_frame = tk.LabelFrame(main_frame, text=T('lbl_video_source'), font=("Arial", 9, "bold"))
        input_frame.pack(fill='x', pady=5, ipady=5)

        self.file_entry = tk.Entry(input_frame)
        self.file_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=5)
        tk.Button(input_frame, text=T('btn_open'), command=self.browse_file, bg='#e1e1e1').pack(side=tk.LEFT, padx=5)

        if TkinterDnD:
            try:

                self.file_entry.drop_target_register(DND_FILES)

                self.file_entry.dnd_bind('<<Drop>>', self.drop_file)

            except Exception:

                logger.warning("tkdnd not available for self.file_entry")

        # ZONE 2: EXTRACTION SETTINGS
        opts_frame = tk.LabelFrame(main_frame, text=T('lbl_params_dest'), font=("Arial", 9, "bold"))
        opts_frame.pack(fill='x', pady=5, ipady=5)

        line1 = tk.Frame(opts_frame)
        line1.pack(fill='x', padx=5, pady=5)
        tk.Label(line1, text=T('lbl_format')).pack(side=tk.LEFT)
        self.format_var = tk.StringVar(value=settings.get('extract_format', 'jpg'))
        ttk.Combobox(line1, textvariable=self.format_var, values=["jpg", "png", "bmp"], width=6, state="readonly").pack(side=tk.LEFT, padx=5)

        self.auto_folder_var = tk.BooleanVar(value=settings.get('extract_auto_folder', True))
        ttk.Checkbutton(line1, text=T('chk_auto_folder'), variable=self.auto_folder_var, command=self.toggle_path_entry).pack(side=tk.LEFT, padx=15)

        self.path_frame = tk.Frame(opts_frame)
        self.path_frame.pack(fill='x', padx=5, pady=0)
        tk.Label(self.path_frame, text=T('lbl_manual_dir')).pack(side=tk.LEFT)
        self.out_dir_var = tk.StringVar()
        self.out_dir_entry = tk.Entry(self.path_frame, textvariable=self.out_dir_var)
        self.out_dir_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=5)
        self.btn_browse_out = tk.Button(self.path_frame, text="...", command=self.browse_out_dir, width=3)
        self.btn_browse_out.pack(side=tk.LEFT)
        self.toggle_path_entry()

        # Ligne 2 : Qualité
        line_quality = tk.LabelFrame(opts_frame, text=T('lbl_quality_frame'), font=("Arial", 8))
        line_quality.pack(fill='x', padx=5, pady=5)

        tk.Label(line_quality, text=T('lbl_jpg_quality')).pack(side=tk.LEFT, padx=5)
        self.jpg_quality_var = tk.IntVar(value=settings.get('extract_jpg_quality', 2))
        self.jpg_quality_scale = tk.Scale(line_quality, from_=1, to=31, orient=tk.HORIZONTAL,
                                           variable=self.jpg_quality_var, length=120, showvalue=True)
        self.jpg_quality_scale.pack(side=tk.LEFT, padx=5)

        tk.Label(line_quality, text=T('lbl_png_compression')).pack(side=tk.LEFT, padx=(20, 5))
        self.png_compression_var = tk.IntVar(value=settings.get('extract_png_compression', 5))
        self.png_compression_scale = tk.Scale(line_quality, from_=0, to=9, orient=tk.HORIZONTAL,
                                               variable=self.png_compression_var, length=100, showvalue=True)
        self.png_compression_scale.pack(side=tk.LEFT, padx=5)

        # Ligne 3 : Fréquence / Mode batch
        line2 = tk.Frame(opts_frame)
        line2.pack(fill='x', padx=5, pady=5)
        tk.Label(line2, text=T('lbl_frequency')).pack(side=tk.LEFT)
        self.mode_var = tk.StringVar(value=settings.get('extract_mode', 'interval'))
        tk.Radiobutton(line2, text=T('rb_interval'), variable=self.mode_var, value="interval", command=self.toggle_inputs).pack(side=tk.LEFT, padx=6)
        tk.Radiobutton(line2, text=T('rb_all_frames'), variable=self.mode_var, value="all", command=self.toggle_inputs).pack(side=tk.LEFT, padx=6)
        tk.Radiobutton(line2, text=T('rb_frame_range'), variable=self.mode_var, value="range", command=self.toggle_inputs).pack(side=tk.LEFT, padx=6)

        self.interval_lbl = tk.Label(line2, text=T('lbl_every'))
        self.interval_lbl.pack(side=tk.LEFT, padx=(5, 0))
        self.interval_entry = tk.Entry(line2, width=5)
        self.interval_entry.insert(0, settings.get('extract_interval', '1'))
        self.interval_entry.pack(side=tk.LEFT, padx=2)
        self.interval_sec_lbl = tk.Label(line2, text=T('lbl_seconds'))
        self.interval_sec_lbl.pack(side=tk.LEFT)

        # Range mode: from/to frame numbers
        self.range_from_lbl = tk.Label(line2, text=T('lbl_from_frame'))
        self.range_from_lbl.pack(side=tk.LEFT, padx=(8, 2))
        self.range_from_var = tk.StringVar(value=settings.get('extract_range_from', '0'))
        self.range_from_entry = tk.Entry(line2, textvariable=self.range_from_var, width=7)
        self.range_from_entry.pack(side=tk.LEFT, padx=2)
        self.range_to_lbl = tk.Label(line2, text=T('lbl_to_frame'))
        self.range_to_lbl.pack(side=tk.LEFT, padx=(4, 2))
        self.range_to_var = tk.StringVar(value=settings.get('extract_range_to', '100'))
        self.range_to_entry = tk.Entry(line2, textvariable=self.range_to_var, width=7)
        self.range_to_entry.pack(side=tk.LEFT, padx=2)

        # Ligne 4 : Extraction frame précise
        single_frame = tk.LabelFrame(opts_frame, text=T('lbl_single_frame_section'), font=("Arial", 8))
        single_frame.pack(fill='x', padx=5, pady=5)

        tk.Label(single_frame, text=T('lbl_timecode')).pack(side=tk.LEFT, padx=5)
        self.single_tc_var = tk.StringVar(value="00:00:00.000")
        self.single_tc_entry = tk.Entry(single_frame, textvariable=self.single_tc_var, width=14)
        self.single_tc_entry.pack(side=tk.LEFT, padx=5)

        tk.Label(single_frame, text=T('lbl_frame_num')).pack(side=tk.LEFT, padx=(10, 5))
        self.single_frame_var = tk.StringVar(value="")
        self.single_frame_entry = tk.Entry(single_frame, textvariable=self.single_frame_var, width=8)
        self.single_frame_entry.pack(side=tk.LEFT, padx=5)
        ToolTip(self.single_frame_entry, "Numéro de frame (ex: 1500). Sera converti en timecode via le FPS.")

        tk.Button(single_frame, text=T('btn_extract_frame'), command=self.extract_single_frame,
                  bg='#17a2b8', fg='white', font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=10)

        # ZONE 3: PROGRESS
        prog_frame = tk.Frame(main_frame)
        prog_frame.pack(fill='x', pady=5)
        self.progress = ttk.Progressbar(prog_frame, orient='horizontal', mode='determinate')
        self.progress.pack(fill='x', pady=5)
        self.lbl_status = tk.Label(prog_frame, text=T('lbl_ready'), fg="blue")
        self.lbl_status.pack()

        # ZONE 4: ACTIONS
        action_frame = tk.Frame(main_frame)
        action_frame.pack(fill='x', pady=10)
        self.btn_start = tk.Button(action_frame, text=T('btn_extract'), command=self.start_extraction, bg='#0066ff', fg='white', font=("Arial", 11, "bold"))
        self.btn_start.pack(side=tk.LEFT, fill='x', expand=True, padx=5)
        self.btn_stop = tk.Button(action_frame, text=T('btn_stop'), command=self.stop_process, bg='#FF0000', fg='white', state='disabled')
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.log_text = scrolledtext.ScrolledText(main_frame, height=8)
        self.log_text.pack(fill='both', expand=True, pady=5)

        # Sync toggle state from loaded settings
        self.toggle_inputs()
        self.toggle_path_entry()

        # Restore output dir if saved
        saved_out = settings.get('extract_out_dir', '')
        if saved_out:
            self.out_dir_entry.config(state='normal')
            self.out_dir_entry.delete(0, tk.END)
            self.out_dir_entry.insert(0, saved_out)
            if self.auto_folder_var.get():
                self.out_dir_entry.config(state='disabled')

    def toggle_path_entry(self):
        state = 'disabled' if self.auto_folder_var.get() else 'normal'
        self.out_dir_entry.config(state=state)
        self.btn_browse_out.config(state=state)

    def toggle_inputs(self):
        mode = self.mode_var.get()
        # Interval controls
        interval_state = 'normal' if mode == 'interval' else 'disabled'
        self.interval_entry.config(state=interval_state)
        self.interval_lbl.config(fg='black' if mode == 'interval' else 'gray')
        self.interval_sec_lbl.config(fg='black' if mode == 'interval' else 'gray')
        # Range controls
        range_state = 'normal' if mode == 'range' else 'disabled'
        self.range_from_entry.config(state=range_state)
        self.range_to_entry.config(state=range_state)
        self.range_from_lbl.config(fg='black' if mode == 'range' else 'gray')
        self.range_to_lbl.config(fg='black' if mode == 'range' else 'gray')

    def _load_video_file(self, f):
        """Shared helper: load video file, set entry + auto-fill frame count."""
        self.file_entry.delete(0, tk.END)
        self.file_entry.insert(0, f)
        if not self.out_dir_var.get():
            self.out_dir_var.set(os.path.dirname(f))
        # Auto-fill frame range in background
        threading.Thread(target=self._autofill_frame_count, args=(f,), daemon=True).start()

    def _autofill_frame_count(self, f):
        """Fetch total frames via ffprobe and fill range_to entry."""
        ffprobe = self.settings.get('ffprobe_path', find_ffprobe())
        total = None
        try:
            cmd = [ffprobe, "-v", "error", "-select_streams", "v:0",
                   "-show_entries", "stream=nb_frames",
                   "-of", "default=nokey=1:noprint_wrappers=1", f]
            out = run_hidden(cmd).stdout.strip()
            if out.isdigit() and int(out) > 0:
                total = int(out)
        except Exception:
            pass
        if total is None:
            try:
                fps = self._get_fps(f)
                dur = self._get_duration(f)
                if fps and dur:
                    total = max(1, int(dur * fps) - 1)
            except Exception:
                pass
        if total is not None:
            self.after(0, lambda t=total: (
                self.range_from_var.set('0'),
                self.range_to_var.set(str(t - 1))
            ))

    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("Video Files", "*.mkv *.mp4 *.avi *.mov *.hevc *.h265 *.264 *.h264 *.ivf *.webm *.ts")])
        if f:
            self._load_video_file(f)

    def drop_file(self, event):
        files = self.winfo_toplevel().tk.splitlist(event.data)
        if files:
            self._load_video_file(files[0])

    def browse_out_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.out_dir_var.set(d)

    def log(self, txt):
        self.after(0, lambda: self._insert_log(txt))

    def _insert_log(self, txt):
        self.log_text.insert(tk.END, txt + "\n")
        self.log_text.see(tk.END)

    def stop_process(self):
        self.stop_event.set()
        self.after(0, lambda: self.lbl_status.config(text="Arrêt demandé..."))

    def _get_fps(self, filename):
        """Get video FPS via ffprobe."""
        ffprobe = self.settings.get('ffprobe_path', find_ffprobe())
        try:
            res = run_hidden([ffprobe, "-v", "error", "-select_streams", "v:0",
                              "-show_entries", "stream=r_frame_rate",
                              "-of", "default=nokey=1:noprint_wrappers=1", filename])
            val = res.stdout.strip()
            if '/' in val:
                num, den = val.split('/')
                return float(num) / float(den) if float(den) != 0 else None
            return float(val) if val else None
        except Exception:
            return None

    def _get_duration(self, filename):
        """Get duration with multiple fallback methods (supports raw HEVC/H264)."""
        ffprobe = self.settings.get('ffprobe_path', find_ffprobe())
        
        # Method 1: format=duration (works for containers like MKV/MP4)
        try:
            res = run_hidden([ffprobe, "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=noprint_wrappers=1:nokey=1", filename])
            val = res.stdout.strip()
            if val and re.match(r'^\d+(\.\d+)?$', val):
                dur = float(val)
                if dur > 0:
                    return dur
        except Exception as e:
            logger.debug(f"format=duration failed: {e}")

        # Method 2: stream=duration (works for some raw streams)
        try:
            res = run_hidden([ffprobe, "-v", "error", "-select_streams", "v:0",
                              "-show_entries", "stream=duration",
                              "-of", "default=noprint_wrappers=1:nokey=1", filename])
            val = res.stdout.strip()
            if val and re.match(r'^\d+(\.\d+)?$', val):
                dur = float(val)
                if dur > 0:
                    return dur
        except Exception as e:
            logger.debug(f"stream=duration failed: {e}")

        # Method 3: Count frames via nb_read_frames (slow but works for raw HEVC)
        try:
            res = run_hidden([ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0",
                              "-show_entries", "stream=nb_read_frames,r_frame_rate",
                              "-of", "csv=p=0", filename])
            parts = res.stdout.strip().split(',')
            if len(parts) >= 2:
                frames_str = parts[0].strip()
                fps_str = parts[1].strip()
                if frames_str.isdigit() and '/' in fps_str:
                    frames = int(frames_str)
                    num, den = map(int, fps_str.split('/'))
                    if den > 0 and frames > 0:
                        dur = frames / (num / den)
                        self.log(f"Durée estimée via comptage frames: {dur:.1f}s ({frames} frames)")
                        return dur
        except Exception as e:
            logger.debug(f"frame count duration failed: {e}")

        return 0.0

    def start_extraction(self):
        video_path = self.file_entry.get()
        fmt = self.format_var.get()

        if not video_path or not os.path.exists(video_path):
            messagebox.showerror("Erreur", "Fichier vidéo invalide.")
            return

        if self.auto_folder_var.get():
            base_folder = os.path.dirname(video_path)
            vid_name = os.path.splitext(os.path.basename(video_path))[0]
            out_dir = os.path.join(base_folder, vid_name)
        else:
            out_dir = self.out_dir_var.get()
            if not out_dir:
                messagebox.showerror("Erreur", "Dossier de sortie manquant.")
                return

        if not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir)
                self.log(f"Dossier créé : {out_dir}")
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible de créer le dossier : {e}")
                return

        self.btn_start.config(state='disabled')
        self.btn_stop.config(state='normal')
        self.stop_event.clear()
        self.log_text.delete("1.0", tk.END)
        self.progress['value'] = 0
        threading.Thread(target=self.process, args=(video_path, out_dir, fmt), daemon=True).start()

    def process(self, video_path, out_dir, fmt):
        root = self.winfo_toplevel()
        try:
            filename = os.path.splitext(os.path.basename(video_path))[0]
            root.after(0, lambda: self.lbl_status.config(text="Analyse de la durée..."))
            total_duration = self._get_duration(video_path)
            if total_duration == 0:
                self.log("⚠️ Impossible de déterminer la durée.")
                total_duration = 1

            self.log(f"Durée totale : {total_duration:.2f} sec")
            self.log(f"Démarrage extraction vers : {out_dir}")

            output_pattern = os.path.join(out_dir, f"{filename}_%04d.{fmt}")
            ffmpeg = self.settings.get('ffmpeg_path', find_ffmpeg())
            cmd = [ffmpeg, "-hide_banner", "-loglevel", "info", "-i", video_path]

            mode = self.mode_var.get()
            if mode == "interval":
                try:
                    sec = float(self.interval_entry.get())
                    if sec <= 0:
                        raise ValueError
                except ValueError:
                    sec = 1.0
                cmd += ["-vf", f"fps=1/{sec}"]
            elif mode == "range":
                try:
                    f_from = int(self.range_from_var.get())
                    f_to = int(self.range_to_var.get())
                    if f_from < 0 or f_to < f_from:
                        raise ValueError
                except ValueError:
                    f_from, f_to = 0, 100
                # select filter: extract all frames between f_from and f_to (inclusive)
                cmd += ["-vf", f"select=between(n\\,{f_from}\\,{f_to})", "-vsync", "vfr"]
            # mode "all": no -vf filter, extract every frame

            if fmt == "jpg":
                cmd += ["-q:v", str(self.jpg_quality_var.get())]
            elif fmt == "png":
                cmd += ["-compression_level", str(self.png_compression_var.get())]

            cmd.append(output_pattern)
            process = popen_hidden(cmd, universal_newlines=True)

            start_time = time.time()
            time_re = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d+)")

            while True:
                if self.stop_event.is_set():
                    process.terminate()
                    break
                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    match = time_re.search(line)
                    if match:
                        h, m, s, ms = match.groups()
                        current_seconds = int(h) * 3600 + int(m) * 60 + int(s) + float(f"0.{ms}")
                        percent = (current_seconds / total_duration) * 100
                        elapsed = time.time() - start_time
                        eta_str = f"{int((elapsed * (100 / percent) - elapsed))}s" if percent > 0 else "?"
                        root.after(0, lambda p=percent, e=eta_str: self._update_progress_ui(p, e))

            if process.returncode == 0 and not self.stop_event.is_set():
                root.after(0, lambda: self._update_progress_ui(100, "0s"))
                root.after(0, lambda: self.lbl_status.config(text="✅ Terminé !"))
                self.log("Extraction terminée avec succès.")
                root.after(0, lambda: messagebox.showinfo("Succès", f"Images extraites dans :\n{out_dir}"))
                threading.Thread(target=notify_toast, args=(T('notif_extract_done'), T('notif_extract_body')), daemon=True).start()
            elif self.stop_event.is_set():
                root.after(0, lambda: self.lbl_status.config(text="🛑 Annulé"))
                self.log("Processus annulé par l'utilisateur.")
            else:
                root.after(0, lambda: self.lbl_status.config(text="❌ Erreur"))
                self.log("Une erreur est survenue.")

        except Exception as e:
            self.log(f"Erreur critique : {str(e)}")
            logger.error(f"Frame extraction error: {e}")
        finally:
            root.after(0, lambda: self.btn_start.config(state='normal'))
            root.after(0, lambda: self.btn_stop.config(state='disabled'))

    def extract_single_frame(self):
        """Extract a single frame at a specific timecode or frame number."""
        video_path = self.file_entry.get()
        if not video_path or not os.path.exists(video_path):
            messagebox.showerror("Erreur", "Fichier vidéo invalide.")
            return

        fmt = self.format_var.get()
        ffmpeg = self.settings.get('ffmpeg_path', find_ffmpeg())
        ffprobe = self.settings.get('ffprobe_path', find_ffprobe())

        # Determine timecode
        timecode = None
        frame_num = self.single_frame_var.get().strip()
        tc_input = self.single_tc_var.get().strip()

        if frame_num and frame_num.isdigit():
            # Convert frame number to timecode using FPS
            try:
                res = run_hidden([ffprobe, "-v", "error", "-select_streams", "v:0",
                                  "-show_entries", "stream=r_frame_rate",
                                  "-of", "default=nokey=1:noprint_wrappers=1", video_path])
                fps_str = res.stdout.strip()
                if '/' in fps_str:
                    num, den = map(int, fps_str.split('/'))
                    fps = num / den if den > 0 else 24
                else:
                    fps = float(fps_str) if fps_str else 24
                total_sec = int(frame_num) / fps
                h = int(total_sec // 3600)
                m = int((total_sec % 3600) // 60)
                s = total_sec % 60
                timecode = f"{h:02d}:{m:02d}:{s:06.3f}"
                self.log(f"Frame {frame_num} → timecode {timecode} (FPS={fps:.3f})")
            except Exception as e:
                self.log(f"Erreur conversion frame→timecode: {e}")
                messagebox.showerror("Erreur", f"Impossible de déterminer le FPS: {e}")
                return
        elif tc_input and tc_input != "00:00:00.000":
            timecode = tc_input
        else:
            messagebox.showwarning("Avertissement", "Entrez un timecode ou un numéro de frame.")
            return

        # Determine output path
        filename = os.path.splitext(os.path.basename(video_path))[0]
        tc_safe = timecode.replace(":", "-").replace(".", "_")
        if self.auto_folder_var.get():
            out_dir = os.path.dirname(video_path)
        else:
            out_dir = self.out_dir_var.get() or os.path.dirname(video_path)

        out_file = os.path.join(out_dir, f"{filename}_frame_{tc_safe}.{fmt}")

        # Build FFmpeg command
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error",
               "-ss", timecode, "-i", video_path,
               "-frames:v", "1"]

        if fmt == "jpg":
            cmd += ["-q:v", str(self.jpg_quality_var.get())]
        elif fmt == "png":
            cmd += ["-compression_level", str(self.png_compression_var.get())]

        cmd += ["-y", out_file]

        self.log(f"Extraction frame à {timecode}...")
        try:
            result = run_hidden(cmd)
            if result.returncode == 0 and os.path.exists(out_file):
                size_kb = os.path.getsize(out_file) / 1024
                self.log(f"✅ Frame extraite : {os.path.basename(out_file)} ({size_kb:.1f} Ko)")
                messagebox.showinfo("Succès", f"Frame extraite :\n{out_file}")
            else:
                err = result.stderr.strip() if result.stderr else "Erreur inconnue"
                self.log(f"❌ Échec extraction : {err}")
                messagebox.showerror("Erreur", f"Échec :\n{err}")
        except Exception as e:
            self.log(f"Erreur critique : {e}")
            messagebox.showerror("Erreur", str(e))

    def _update_progress_ui(self, percent, eta):
        self.progress['value'] = percent
        self.lbl_status.config(text=f"Progression : {percent:.1f}% | ETA : {eta}")


# ============================================================================
# [NEW] MEDIA INFO TAB
# ============================================================================

class MediaInfoTab(ttk.Frame):
    """Quick file analysis tab showing full track details in a tree view."""

    def __init__(self, notebook, settings):
        super().__init__(notebook)
        self.settings = settings
        self.pack(fill='both', expand=True)

        main_frame = tk.Frame(self)
        main_frame.pack(padx=10, pady=10, fill='both', expand=True)

        # File selection
        input_frame = tk.Frame(main_frame)
        input_frame.pack(fill='x', pady=5)
        tk.Label(input_frame, text="Fichier :").pack(side=tk.LEFT)
        self.file_entry = tk.Entry(input_frame)
        self.file_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=5)
        tk.Button(input_frame, text="Ouvrir", command=self.browse_file, bg='#e1e1e1').pack(side=tk.LEFT, padx=5)
        tk.Button(input_frame, text=T('btn_analyze_file'), command=self.analyze, bg='#0066ff', fg='white').pack(side=tk.LEFT, padx=5)

        if TkinterDnD:
            try:

                self.file_entry.drop_target_register(DND_FILES)

                self.file_entry.dnd_bind('<<Drop>>', self.drop_file)

            except Exception:

                logger.warning("tkdnd not available for self.file_entry")

        # Info tree
        tree_frame = tk.Frame(main_frame)
        tree_frame.pack(fill='both', expand=True, pady=5)

        columns = ("Propriété", "Valeur")
        self.info_tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings", height=20)
        self.info_tree.heading("#0", text="")
        self.info_tree.heading("Propriété", text="Propriété")
        self.info_tree.heading("Valeur", text="Valeur")
        self.info_tree.column("#0", width=30)
        self.info_tree.column("Propriété", width=200)
        self.info_tree.column("Valeur", width=500)
        self.info_tree.pack(side=tk.LEFT, fill='both', expand=True)

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.info_tree.yview)
        sb.pack(side=tk.RIGHT, fill='y')
        self.info_tree.configure(yscrollcommand=sb.set)

        # Summary label
        self.summary_lbl = tk.Label(main_frame, text="", font=("Arial", 10, "italic"), fg="gray")
        self.summary_lbl.pack(pady=5)

    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("MKV/Video Files", "*.mkv *.mp4 *.avi *.mov *.webm")])
        if f:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, f)
            self.analyze()

    def drop_file(self, event):
        files = self.winfo_toplevel().tk.splitlist(event.data)
        if files:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, files[0])
            self.analyze()

    def analyze(self):
        filepath = self.file_entry.get()
        if not filepath or not os.path.exists(filepath):
            messagebox.showwarning("Avertissement", "Fichier invalide.")
            return

        self.info_tree.delete(*self.info_tree.get_children())

        mkvmerge = self.parent_app.mkvmerge_path_entry.get() if hasattr(self, 'parent_app') and hasattr(self.parent_app, 'mkvmerge_path_entry') else self.settings.get('mkvmerge_path', 'mkvmerge')
        try:
            res = run_hidden([mkvmerge, "-J", filepath])
            info = json.loads(res.stdout)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de lire le fichier : {e}")
            return

        # File info
        file_node = self.info_tree.insert("", "end", text="📄", values=("Fichier", os.path.basename(filepath)))
        file_size = os.path.getsize(filepath)
        size_str = f"{file_size / (1024 * 1024):.1f} Mo" if file_size > 1024 * 1024 else f"{file_size / 1024:.1f} Ko"
        self.info_tree.insert(file_node, "end", values=("Taille", size_str))

        container = info.get("container", {})
        if container.get("properties", {}).get("duration"):
            dur_ns = container["properties"]["duration"]
            dur_sec = dur_ns / 1_000_000_000
            h = int(dur_sec // 3600)
            m = int((dur_sec % 3600) // 60)
            s = int(dur_sec % 60)
            self.info_tree.insert(file_node, "end", values=("Durée", f"{h:02d}:{m:02d}:{s:02d}"))

        if container.get("properties", {}).get("title"):
            self.info_tree.insert(file_node, "end", values=("Titre", container["properties"]["title"]))

        # Tracks
        track_counts = {"video": 0, "audio": 0, "subtitles": 0}
        track_icons = {"video": "🎬", "audio": "🔊", "subtitles": "💬"}

        for track in info.get("tracks", []):
            ttype = track["type"]
            track_counts[ttype] = track_counts.get(ttype, 0) + 1
            props = track.get("properties", {})
            tid = track["id"]
            codec = track.get("codec", "?")
            lang = props.get("language", "und")
            name = props.get("track_name", "")
            icon = track_icons.get(ttype, "📎")
            label = f"{ttype.capitalize()} #{tid} — {codec} [{lang}]"
            if name:
                label += f" — {name}"

            node = self.info_tree.insert("", "end", text=icon, values=("Piste", label))
            self.info_tree.insert(node, "end", values=("ID", tid))
            self.info_tree.insert(node, "end", values=("Codec", codec))
            self.info_tree.insert(node, "end", values=("Langue", lang))
            if name:
                self.info_tree.insert(node, "end", values=("Nom", name))
            self.info_tree.insert(node, "end", values=("Par défaut", "Oui" if props.get("default_track") else "Non"))
            self.info_tree.insert(node, "end", values=("Forcé", "Oui" if props.get("forced_track") else "Non"))

            if ttype == "video":
                if props.get("pixel_dimensions"):
                    self.info_tree.insert(node, "end", values=("Résolution", props["pixel_dimensions"]))
                if props.get("display_dimensions"):
                    self.info_tree.insert(node, "end", values=("Affichage", props["display_dimensions"]))
            elif ttype == "audio":
                if props.get("audio_channels"):
                    ch = props["audio_channels"]
                    ch_label = {1: "Mono", 2: "Stéréo", 6: "5.1", 8: "7.1"}.get(ch, f"{ch} canaux")
                    self.info_tree.insert(node, "end", values=("Canaux", ch_label))
                if props.get("audio_sampling_frequency"):
                    self.info_tree.insert(node, "end", values=("Fréquence", f"{props['audio_sampling_frequency']} Hz"))

        # Attachments
        for att in info.get("attachments", []):
            node = self.info_tree.insert("", "end", text="📎", values=("Pièce jointe", att.get("file_name", "?")))
            self.info_tree.insert(node, "end", values=("Type MIME", att.get("content_type", "?")))
            if att.get("size"):
                self.info_tree.insert(node, "end", values=("Taille", f"{att['size'] / 1024:.1f} Ko"))

        # Chapters
        if info.get("chapters"):
            total_chapters = sum(e.get("num_entries", 0) for e in info["chapters"])
            if total_chapters > 0:
                self.info_tree.insert(file_node, "end", values=("Chapitres", str(total_chapters)))

        # Summary
        summary = f"📊 {track_counts.get('video', 0)} vidéo, {track_counts.get('audio', 0)} audio, {track_counts.get('subtitles', 0)} sous-titres, {len(info.get('attachments', []))} pièces jointes"
        self.summary_lbl.config(text=summary)

        # Expand all
        for item in self.info_tree.get_children():
            self.info_tree.item(item, open=True)


# ============================================================================
# METADATA PICKER DIALOG — choose cover/description source per provider
# ============================================================================

class MetadataPickerDialog(tk.Toplevel):
    """Modal dialog: choose cover art, short description, long synopsis per provider.
    Works on one file (selected in rename_tree) with 'apply to all' option.
    """

    IMG_W, IMG_H = 140, 200   # thumbnail display size

    def __init__(self, parent, filepath, file_results, settings, lang_tvdb, lang_tmdb,
                 batch_pro_tab=None):
        super().__init__(parent)
        self.title(T('bp_picker_title'))
        # Restore saved size (WxH only), always center on screen
        saved_size = settings.get('bp_picker_geometry', '1200x740') if settings else '1200x740'
        try:
            size_part = saved_size.split('+')[0]  # strip position if present
            pw, ph = map(int, size_part.split('x'))
        except Exception:
            pw, ph = 1200, 740
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        px = (sw - pw) // 2
        py = max(0, (sh - ph) // 2)
        self.geometry(f"{pw}x{ph}+{px}+{py}")
        self.minsize(800, 500)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.filepath = filepath
        self.file_results = file_results
        self.settings = settings
        self.lang_tvdb = lang_tvdb
        self.lang_tmdb = lang_tmdb
        self.batch_pro_tab = batch_pro_tab
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Data fetched per provider: {pname: {name, description, poster_url, still_url}}
        self.provider_meta = {}
        self.provider_images = {}   # pname -> PhotoImage (keep reference!)

        # Selection variables — restore from per-file prefs first, then global fallback
        per_file_prefs = (file_results.get(filepath, {}).get('picker_prefs', {})
                          if file_results and filepath else {})
        saved_prefs = per_file_prefs or (settings.get('bp_picker_prefs', {}) if settings else {})
        self.cover_var = tk.StringVar(value=saved_prefs.get('cover_src', ''))
        self.desc_var = tk.StringVar(value=saved_prefs.get('desc_src', ''))
        self.synopsis_var = tk.StringVar(value=saved_prefs.get('synopsis_src', ''))
        self.cast_src_var = tk.StringVar(value=saved_prefs.get('cast_src', ''))
        self.genre_src_var = tk.StringVar(value=saved_prefs.get('genre_src', ''))
        self.crew_src_var = tk.StringVar(value=saved_prefs.get('crew_src', ''))
        self.apply_all_var = tk.BooleanVar(value=False)

        self._build_ui()
        threading.Thread(target=self._fetch_all_meta, daemon=True).start()

    def _build_ui(self):
        fname = os.path.basename(self.filepath)
        tk.Label(self, text=fname, font=("Arial", 9, "italic"),
                 fg='gray', wraplength=1150).pack(padx=10, pady=(6, 2))

        # Provider columns — direct frame, dialog wide enough for 3 columns
        self.cols_frame = tk.Frame(self)
        self.cols_frame.pack(fill='both', expand=True, padx=8, pady=4)

        self.loading_lbl = tk.Label(self.cols_frame, text=T('bp_picker_loading'),
                                    fg='gray', font=("Arial", 11))
        self.loading_lbl.pack(pady=30)

        # Bottom controls
        bot = tk.Frame(self)
        bot.pack(fill='x', padx=10, pady=6)
        ttk.Checkbutton(bot, text=T('bp_picker_apply_all'),
                        variable=self.apply_all_var).pack(side='left', padx=5)
        tk.Button(bot, text="OK", command=self._on_ok,
                  bg='#28a745', fg='white', width=10).pack(side='right', padx=5)
        tk.Button(bot, text="Annuler", command=self.destroy,
                  bg='#dc3545', fg='white', width=10).pack(side='right', padx=5)

    def _fetch_all_meta(self):
        """Fetch meta from each provider that has a match."""
        res = self.file_results.get(self.filepath, {})
        parsed = res.get('parsed', {})
        all_pr = res.get('all_provider_results', {})

        tvdb_key = self.settings.get('tvdb_api_key', '')
        tmdb_key = self.settings.get('tmdb_api_key', '')

        for pname, match in all_pr.items():
            sid = match.get('id')
            if not sid:
                continue
            meta = {}
            try:
                if pname == 'TVDB' and tvdb_key:
                    prov = TVDBProvider(tvdb_key, self.lang_tvdb)
                    if parsed.get('kind') == 'series':
                        meta = prov.get_episode_meta(sid, parsed['season'], parsed['episode'])
                        meta['poster_url'] = prov.get_series_poster(sid)
                    meta['series_name'] = match.get('name', '')
                elif pname == 'TMDB' and tmdb_key:
                    prov = TMDBProvider(tmdb_key, self.lang_tmdb)
                    if parsed.get('kind') == 'series':
                        meta = prov.get_episode_meta(sid, parsed['season'], parsed['episode'])
                        meta['poster_url'] = prov.get_series_poster(sid)
                    else:
                        meta = prov.get_movie_meta(sid)
                    meta['series_name'] = match.get('name', '')
                elif pname == 'TVmaze':
                    prov = TVmazeProvider()
                    if parsed.get('kind') == 'series':
                        meta = prov.get_episode_meta(sid, parsed['season'], parsed['episode'])
                    meta['series_name'] = match.get('name', '')
            except Exception as e:
                logger.debug(f"Picker fetch {pname}: {e}")
                meta = {}

            if meta:
                # Also fetch series meta (genres, rating, IMDB)
                if prov and hasattr(prov, 'get_series_meta'):
                    try:
                        s_meta = prov.get_series_meta(sid)
                        for k, v in s_meta.items():
                            if v and not meta.get(k):
                                meta[k] = v
                    except Exception as e:
                        logger.debug(f"Picker series_meta {pname}: {e}")
                # Fetch cast (episode-level first, then series-level)
                ep_id = meta.get('episode_id')
                if ep_id and prov and hasattr(prov, 'get_episode_extended'):
                    try:
                        ext = prov.get_episode_extended(ep_id)
                        if ext.get('cast'):
                            meta['cast'] = ext['cast']
                    except Exception as e:
                        logger.debug(f"Picker ep_extended {pname}: {e}")
                if not meta.get('cast') and prov and hasattr(prov, 'get_episode_cast'):
                    try:
                        meta['cast'] = prov.get_episode_cast(
                            sid, parsed.get('season', 1), parsed.get('episode', 1))
                    except Exception as e:
                        logger.debug(f"Picker ep_cast {pname}: {e}")
                self.provider_meta[pname] = meta

        self.after(0, self._render_columns)

    def _render_columns(self):
        """Build provider columns with image + description choices."""
        self.loading_lbl.destroy()

        if not self.provider_meta:
            tk.Label(self.cols_frame,
                     text="Aucune donnée disponible (vérifiez vos clés API)",
                     fg='red').pack(pady=20)
            return

        providers = list(self.provider_meta.keys())
        # Resize dialog width to fit number of columns (min 400px per col)
        n = len(providers)
        needed_w = max(800, n * 400)
        cur_geo = self.geometry()
        try:
            cur_w, rest = cur_geo.split('x', 1)
            cur_h = rest.split('+')[0]
            if int(cur_w) < needed_w:
                self.geometry(f"{needed_w}x{cur_h}")
        except Exception:
            pass

        for pname in providers:
            meta = self.provider_meta[pname]
            col = tk.LabelFrame(self.cols_frame, text=f"  {pname}  ",
                                font=("Arial", 10, "bold"), padx=6, pady=4)
            col.pack(side='left', fill='both', expand=True, padx=4)

            # Image area
            img_frame = tk.Frame(col, width=self.IMG_W + 4, height=self.IMG_H + 4,
                                 relief='sunken', bd=1)
            img_frame.pack(pady=(4, 0))
            img_frame.pack_propagate(False)
            img_lbl = tk.Label(img_frame, text="⏳", fg='gray')
            img_lbl.pack(expand=True)

            dim_lbl = tk.Label(col, text="", fg='gray', font=("Arial", 7))
            dim_lbl.pack()

            cover_url = meta.get('poster_url') or meta.get('still_url', '')
            if cover_url:
                threading.Thread(
                    target=self._load_image,
                    args=(pname, cover_url, img_lbl, dim_lbl),
                    daemon=True
                ).start()

            # Cover radio
            r_cover = ttk.Radiobutton(col, text=T('bp_picker_cover'),
                                      variable=self.cover_var, value=pname)
            r_cover.pack(anchor='w')

            # Description
            desc = meta.get('description', '')
            tk.Label(col, text=T('bp_picker_desc') + ":",
                     font=("Arial", 8, "bold")).pack(anchor='w', pady=(6, 0))
            desc_box = tk.Text(col, height=3, wrap='word', font=("Arial", 8),
                               relief='flat', bg='#f8f8f8')
            desc_box.insert('1.0', desc)
            desc_box.config(state='disabled')
            desc_box.pack(fill='x', pady=2)
            ttk.Radiobutton(col, text="Utiliser cette description",
                            variable=self.desc_var, value=pname).pack(anchor='w')

            # Long synopsis — use description if provider has only one field
            # TVDB/TMDB both expose overview as description; use same or leave empty
            tk.Label(col, text=T('bp_picker_synopsis') + ":",
                     font=("Arial", 8, "bold")).pack(anchor='w', pady=(6, 0))
            syn_box = tk.Text(col, height=5, wrap='word', font=("Arial", 8),
                              relief='flat', bg='#f8f8f8')
            syn_box.insert('1.0', desc)   # same field — user can edit after if needed
            syn_box.config(state='disabled')
            syn_box.pack(fill='x', pady=2)
            ttk.Radiobutton(col, text="Utiliser ce synopsis",
                            variable=self.synopsis_var, value=pname).pack(anchor='w')

            # Cast / Artist
            full_cast = meta.get('cast', [])
            crew_markers = ('__director__', '__writer__', '__producer__', '__studio__')
            actors = [a for a in full_cast if a.get('role') not in crew_markers]
            directors = [a['name'] for a in full_cast if a.get('role') == '__director__']
            writers = [a['name'] for a in full_cast if a.get('role') == '__writer__']
            producers = [a['name'] for a in full_cast if a.get('role') == '__producer__']
            studios = [a['name'] for a in full_cast if a.get('role') == '__studio__']

            if actors:
                tk.Label(col, text=T('bp_picker_cast') + ":",
                         font=("Arial", 8, "bold")).pack(anchor='w', pady=(6, 0))
                cast_text = ", ".join(a['name'] for a in actors[:6] if a.get('name'))
                if len(actors) > 6:
                    cast_text += f" (+{len(actors)-6})"
                tk.Label(col, text=cast_text, wraplength=360,
                         font=("Arial", 8), fg='#333').pack(anchor='w', padx=4)
                ttk.Radiobutton(col, text="Utiliser ce cast (Artiste/Interprète)",
                                variable=self.cast_src_var, value=pname).pack(anchor='w')

            # Crew (director / writer / producer / studio)
            if directors or writers or producers or studios:
                tk.Label(col, text="Réal. / Scénario / Producteur / Studio:",
                         font=("Arial", 8, "bold")).pack(anchor='w', pady=(6, 0))
                crew_lines = []
                if directors:
                    crew_lines.append("Réal.: " + ", ".join(directors[:3]))
                if writers:
                    crew_lines.append("Scénar.: " + ", ".join(writers[:3]))
                if producers:
                    crew_lines.append("Prod.: " + ", ".join(producers[:4]))
                if studios:
                    crew_lines.append("Studio: " + ", ".join(studios[:3]))
                tk.Label(col, text="\n".join(crew_lines), wraplength=360,
                         font=("Arial", 8), fg='#333', justify='left').pack(anchor='w', padx=4)
                ttk.Radiobutton(col, text="Utiliser ce crew (Réal./Prod./Studio)",
                                variable=self.crew_src_var, value=pname).pack(anchor='w')
            else:
                tk.Label(col, text="(pas de crew — utiliser TMDB)",
                         font=("Arial", 7, "italic"), fg='gray').pack(anchor='w', padx=4)

            # Genres
            genres = meta.get('genres', [])
            if genres:
                tk.Label(col, text=T('bp_picker_genres') + ":",
                         font=("Arial", 8, "bold")).pack(anchor='w', pady=(6, 0))
                tk.Label(col, text=", ".join(genres),
                         font=("Arial", 8), fg='#333', wraplength=360).pack(anchor='w', padx=4)
                ttk.Radiobutton(col, text="Utiliser ces genres",
                                variable=self.genre_src_var, value=pname).pack(anchor='w')

            # Air date & content rating (info only)
            info_parts = []
            if meta.get('aired'):
                info_parts.append(f"Date: {meta['aired']}")
            if meta.get('content_rating'):
                info_parts.append(f"Rating: {meta['content_rating']}")
            if meta.get('imdb_id'):
                info_parts.append(f"IMDB: {meta['imdb_id']}")
            if info_parts:
                tk.Label(col, text="  ".join(info_parts),
                         font=("Arial", 7), fg='gray').pack(anchor='w', pady=(4, 0))

        # Set defaults: use saved choice if provider available, else first provider
        if providers:
            for var in (self.cover_var, self.desc_var, self.synopsis_var,
                        self.cast_src_var, self.genre_src_var):
                if var.get() not in providers:
                    var.set(providers[0])
            # crew_src default = first provider that actually has crew (usually TMDB)
            crew_providers = [p for p in providers
                              if any(a.get('role') in ('__director__', '__writer__', '__producer__', '__studio__')
                                     for a in self.provider_meta[p].get('cast', []))]
            if self.crew_src_var.get() not in crew_providers:
                self.crew_src_var.set(crew_providers[0] if crew_providers else providers[0])

    def _load_image(self, pname, url, label, dim_lbl=None):
        """Download and resize image, update label + show original dimensions."""
        try:
            import io
            req = urllib.request.Request(url,
                                         headers={'User-Agent': 'PyMkvPropEdit/3.7'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            img = Image.open(io.BytesIO(data))
            orig_w, orig_h = img.size
            img.thumbnail((self.IMG_W, self.IMG_H), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.provider_images[pname] = photo  # prevent GC
            dim_text = f"{orig_w}×{orig_h}px"
            self.after(0, lambda: label.config(image=photo, text=''))
            if dim_lbl:
                self.after(0, lambda: dim_lbl.config(text=dim_text))
        except Exception as e:
            logger.debug(f"Picker image load {pname}: {e}")
            self.after(0, lambda: label.config(text="❌ img"))

    def _save_picker_geometry(self):
        """Persist picker size (WxH only, not position) to settings."""
        try:
            geo = self.geometry()
            size = geo.split('+')[0]  # "1200x740" only, drop position
            if self.settings is not None:
                self.settings['bp_picker_geometry'] = size
        except Exception:
            pass

    def _on_window_close(self):
        self._save_picker_geometry()
        self.destroy()

    def _on_ok(self):
        """Apply choices to file_results and close.

        Single file: apply fetched content directly to chosen dict.
        Apply-to-all: store SOURCE PREFS at batch_pro_tab level so each file
        fetches its OWN episode-specific content at pipeline time.
        """
        cover_src = self.cover_var.get()
        desc_src = self.desc_var.get()
        syn_src = self.synopsis_var.get()
        cast_src = self.cast_src_var.get()
        genre_src = self.genre_src_var.get()
        crew_src = self.crew_src_var.get()

        crew_markers = ('__director__', '__writer__', '__producer__', '__studio__')

        # Apply fetched content to the current file immediately
        chosen = self.file_results.get(self.filepath, {}).get('chosen', {})
        if cover_src and cover_src in self.provider_meta:
            m = self.provider_meta[cover_src]
            chosen['cover_url'] = m.get('poster_url') or m.get('still_url', '')
        if desc_src and desc_src in self.provider_meta:
            chosen['description'] = self.provider_meta[desc_src].get('description', '')
        if syn_src and syn_src in self.provider_meta:
            chosen['synopsis'] = self.provider_meta[syn_src].get('description', '')
        # Merge actors (cast_src) + crew (crew_src) into a single cast list
        merged_cast = []
        if cast_src and cast_src in self.provider_meta:
            merged_cast += [a for a in self.provider_meta[cast_src].get('cast', [])
                            if a.get('role') not in crew_markers]
        if crew_src and crew_src in self.provider_meta:
            merged_cast += [a for a in self.provider_meta[crew_src].get('cast', [])
                            if a.get('role') in crew_markers]
        if merged_cast:
            chosen['cast'] = merged_cast
        if genre_src and genre_src in self.provider_meta:
            chosen['genres'] = self.provider_meta[genre_src].get('genres', [])
        if self.filepath in self.file_results:
            self.file_results[self.filepath]['chosen'] = chosen

        if self.batch_pro_tab is not None:
            if self.apply_all_var.get():
                # Store SOURCE PREFS — pipeline will fetch per-episode content for each file
                self.batch_pro_tab.meta_picker_prefs = {
                    'cover_src': cover_src,
                    'desc_src': desc_src,
                    'synopsis_src': syn_src,
                    'cast_src': cast_src,
                    'genre_src': genre_src,
                    'crew_src': crew_src,
                }
            else:
                # apply-all not checked: per-file choice already saved to file_results
                # clear any leftover apply-all prefs so they don't override per-file choices
                self.batch_pro_tab.meta_picker_prefs = {}

        # Save per-file prefs (so re-opening picker for the same file restores ITS choices)
        prefs_dict = {
            'cover_src': cover_src, 'desc_src': desc_src,
            'synopsis_src': syn_src, 'cast_src': cast_src,
            'genre_src': genre_src, 'crew_src': crew_src,
        }
        if self.filepath and self.file_results and self.filepath in self.file_results:
            self.file_results[self.filepath]['picker_prefs'] = prefs_dict
        # Also persist to global settings as default for NEW files (not re-opened ones)
        if self.settings is not None:
            self.settings['bp_picker_prefs'] = prefs_dict
        self._save_picker_geometry()
        self.destroy()


# ============================================================================
# BATCH PRO TAB — Auto-rename (TVDB/TMDB/TVmaze) + track reorder + sync pipeline
# ============================================================================

class BatchProTab(ttk.Frame, AudioSyncMixin):
    def __init__(self, notebook, settings, parent_app):
        super().__init__(notebook)
        self.settings = settings
        self.parent_app = parent_app
        self.pack(fill='both', expand=True)
        self.temp_files = []
        self.file_results = {}     # filepath -> {parsed, meta, matches, chosen, newname, all_provider_results}
        self.track_template = []   # list of {type, lang, forced}
        self.meta_picker_prefs = {}   # source prefs from MetadataPickerDialog "apply to all"

        # PanedWindow vertical — chaque section redimensionnable par l'utilisateur
        paned = tk.PanedWindow(self, orient=tk.VERTICAL, sashrelief='flat',
                               sashpad=0, sashwidth=4, bg='#999999')
        paned.pack(fill='both', expand=True, padx=2, pady=2)
        self.bp_paned = paned
        self._pane_init_done = False
        self.after(400, self._init_pane_sizes)

        # ── SECTION 1: FILES ──────────────────────────────────────────
        sec1 = tk.LabelFrame(paned, text=T('bp_step1'), font=("Arial", 10, "bold"),
                             fg='#0066cc', padx=5, pady=3)

        lb_frame = tk.Frame(sec1)
        lb_frame.pack(fill='both', expand=True)
        self.file_list = tk.Listbox(lb_frame, selectmode=tk.MULTIPLE, height=4)
        self.file_list.pack(side='left', fill='both', expand=True)
        sb1 = ttk.Scrollbar(lb_frame, orient='vertical', command=self.file_list.yview)
        sb1.pack(side='right', fill='y')
        self.file_list.configure(yscrollcommand=sb1.set)
        if TkinterDnD is not None:
            try:
                self.file_list.drop_target_register(DND_FILES)
                self.file_list.dnd_bind('<<Drop>>', self._drop_files)
            except Exception:
                pass

        bf = tk.Frame(sec1)
        bf.pack(fill='x', pady=2)
        tk.Button(bf, text=T('btn_add_files'), command=self._add_files, bg='#ADD8E6').pack(side='left', padx=3)
        tk.Button(bf, text=T('btn_add_folder'), command=self._add_folder, bg='#800080', fg='white').pack(side='left', padx=3)
        tk.Button(bf, text=T('btn_remove'), command=self._remove_selected, bg='#FF4500', fg='white').pack(side='left', padx=3)
        tk.Button(bf, text=T('btn_clear'), command=self._clear_files, bg='#FF0000', fg='white').pack(side='left', padx=3)

        paned.add(sec1, minsize=80, height=115)

        # ── SECTION 2: AUTO-RENAME ────────────────────────────────────
        sec2 = tk.LabelFrame(paned, text=T('bp_step2'), font=("Arial", 10, "bold"),
                             fg='#0066cc', padx=5, pady=3)

        srow = tk.Frame(sec2)
        srow.pack(fill='x', pady=1)
        tk.Label(srow, text=T('bp_lang_search')).pack(side='left')
        self.search_lang_var = tk.StringVar(value=settings.get('bp_search_lang', 'fr'))
        ttk.Combobox(srow, textvariable=self.search_lang_var,
                     values=['fr', 'en', 'ja', 'de', 'es', 'it'],
                     width=5, state='readonly').pack(side='left', padx=5)
        tk.Label(srow, text="API:").pack(side='left', padx=(8, 0))
        self.bp_api_var = tk.StringVar(value=settings.get('bp_api_provider', 'Auto'))
        ttk.Combobox(srow, textvariable=self.bp_api_var,
                     values=['Auto', 'TVDB', 'TMDB', 'TVmaze'],
                     width=8, state='readonly').pack(side='left', padx=5)
        tk.Button(srow, text=T('bp_search_names'), command=self._search_names,
                  bg='#17a2b8', fg='white', font=("Arial", 9, "bold")).pack(side='left', padx=8)
        self.bp_picker_btn = tk.Button(srow, text="🎨 Illus./Desc.",
                                       command=self._open_meta_picker,
                                       bg='#9b59b6', fg='white',
                                       font=("Arial", 9, "bold"))
        self.bp_picker_btn.pack(side='left', padx=4)
        self.bp_search_status = tk.Label(srow, text="", fg='gray', font=("Arial", 8, "italic"))
        self.bp_search_status.pack(side='left', padx=5)

        rt_frame = tk.Frame(sec2)
        rt_frame.pack(fill='both', expand=True, pady=2)
        cols = ('file', 'detected', 'newname', 'status')
        self.rename_tree = ttk.Treeview(rt_frame, columns=cols, show='headings', height=4)
        self.rename_tree.heading('file', text=T('bp_col_file'))
        self.rename_tree.heading('detected', text=T('bp_col_detected'))
        self.rename_tree.heading('newname', text=T('bp_col_newname'))
        self.rename_tree.heading('status', text=T('bp_col_status'))
        self.rename_tree.column('file', width=240)
        self.rename_tree.column('detected', width=130)
        self.rename_tree.column('newname', width=300)
        self.rename_tree.column('status', width=100, anchor='center')
        self.rename_tree.pack(side='left', fill='both', expand=True)
        sb2 = ttk.Scrollbar(rt_frame, orient='vertical', command=self.rename_tree.yview)
        sb2.pack(side='right', fill='y')
        self.rename_tree.configure(yscrollcommand=sb2.set)
        self.rename_tree.bind('<Double-1>', self._on_rename_edit)

        meta_row = tk.Frame(sec2)
        meta_row.pack(fill='x', pady=1)
        self.bp_embed_meta_var = tk.BooleanVar(value=settings.get('bp_embed_meta', False))
        ttk.Checkbutton(meta_row, text=T('bp_chk_embed_meta'),
                        variable=self.bp_embed_meta_var).pack(side='left', padx=5)
        self.bp_clean_tags_var = tk.BooleanVar(value=settings.get('bp_clean_tags', True))
        ttk.Checkbutton(meta_row, text="Supprimer anciens tags/cover avant",
                        variable=self.bp_clean_tags_var).pack(side='left', padx=8)
        tk.Label(meta_row, text="(cliquer 🎨 pour choisir les sources)",
                 fg='gray', font=("Arial", 8, "italic")).pack(side='left', padx=5)

        paned.add(sec2, minsize=90, height=170)

        # ── SECTION 3: TRACK ORDER ────────────────────────────────────
        sec3 = tk.LabelFrame(paned, text=T('bp_step3'), font=("Arial", 10, "bold"),
                             fg='#0066cc', padx=5, pady=3)

        tk.Label(sec3, text=T('bp_reorder_hint'), fg='gray',
                 font=("Arial", 8, "italic")).pack(anchor='w')

        torow = tk.Frame(sec3)
        torow.pack(fill='x', pady=1)
        tk.Button(torow, text=T('bp_load_ref'), command=self._load_ref_tracks,
                  bg='#e1e1e1').pack(side='left', padx=3)
        tk.Button(torow, text=T('bp_load_first'), command=self._load_first_file_ref_tracks,
                  bg='#90EE90').pack(side='left', padx=3)
        tk.Button(torow, text=T('bp_track_up'), command=lambda: self._move_track(-1),
                  bg='#FFC107').pack(side='left', padx=3)
        tk.Button(torow, text=T('bp_track_down'), command=lambda: self._move_track(1),
                  bg='#FFC107').pack(side='left', padx=3)

        tt_frame = tk.Frame(sec3)
        tt_frame.pack(fill='both', expand=True, pady=2)
        tcols = ('track', 'type', 'codec', 'lang', 'name', 'forced', 'default')
        self.track_tree = ttk.Treeview(tt_frame, columns=tcols, show='headings', height=5)
        self.track_tree.heading('track', text=T('bp_col_track'))
        self.track_tree.heading('type', text=T('bp_col_type'))
        self.track_tree.heading('codec', text=T('bp_col_codec'))
        self.track_tree.heading('lang', text=T('bp_col_lang'))
        self.track_tree.heading('name', text=T('bp_col_name_tr'))
        self.track_tree.heading('forced', text=T('bp_col_forced'))
        self.track_tree.heading('default', text=T('bp_col_default'))
        self.track_tree.column('track', width=45, anchor='center')
        self.track_tree.column('type', width=80, anchor='center')
        self.track_tree.column('codec', width=70, anchor='center')
        self.track_tree.column('lang', width=60, anchor='center')
        self.track_tree.column('name', width=240)
        self.track_tree.column('forced', width=55, anchor='center')
        self.track_tree.column('default', width=60, anchor='center')
        self.track_tree.pack(side='left', fill='both', expand=True)
        sb3 = ttk.Scrollbar(tt_frame, orient='vertical', command=self.track_tree.yview)
        sb3.pack(side='right', fill='y')
        self.track_tree.configure(yscrollcommand=sb3.set)

        paned.add(sec3, minsize=90, height=155)

        # ── SECTION 4: PIPELINE ───────────────────────────────────────
        sec4 = tk.LabelFrame(paned, text=T('bp_step4'), font=("Arial", 10, "bold"),
                             fg='#0066cc', padx=5, pady=3)
        paned.add(sec4, minsize=130)

        opts = tk.Frame(sec4)
        opts.pack(fill='x', pady=1)
        self.bp_sync_var = tk.BooleanVar(value=settings.get('bp_sync', True))
        self.bp_sync_subs_var = tk.BooleanVar(value=settings.get('bp_sync_subs', True))
        self.bp_props_var = tk.BooleanVar(value=settings.get('bp_props', True))
        self.bp_reorder_var = tk.BooleanVar(value=settings.get('bp_reorder', False))
        self.bp_rename_var = tk.BooleanVar(value=settings.get('bp_rename', True))
        ttk.Checkbutton(opts, text=T('bp_chk_sync'), variable=self.bp_sync_var).pack(side='left', padx=6)
        ttk.Checkbutton(opts, text="+ sous-titres", variable=self.bp_sync_subs_var).pack(side='left', padx=0)
        ttk.Separator(opts, orient='vertical').pack(side='left', fill='y', padx=6)
        ttk.Checkbutton(opts, text=T('bp_chk_props'), variable=self.bp_props_var).pack(side='left', padx=6)
        ttk.Checkbutton(opts, text=T('bp_chk_reorder'), variable=self.bp_reorder_var).pack(side='left', padx=6)
        ttk.Checkbutton(opts, text=T('bp_chk_rename'), variable=self.bp_rename_var).pack(side='left', padx=6)

        self.bp_preserve_src_var = tk.BooleanVar(value=settings.get('bp_preserve_src', False))
        ttk.Checkbutton(opts, text=T('bp_chk_preserve'), variable=self.bp_preserve_src_var).pack(side='left', padx=6)

        srow2 = tk.Frame(sec4)
        srow2.pack(fill='x', pady=1)
        tk.Label(srow2, text=T('lbl_ref_lang')).pack(side='left')
        # Map a saved code or label to a full LANGUAGES label
        _saved_ref = settings.get('bp_ref_lang', 'jpn')
        _ref_label = next((l for l in LANGUAGES if l.split()[0] == _saved_ref.split()[0]),
                          'jpn (Japanese)')
        self.bp_ref_lang_var = tk.StringVar(value=_ref_label)
        ttk.Combobox(srow2, textvariable=self.bp_ref_lang_var, values=LANGUAGES,
                     state='readonly', width=16).pack(side='left', padx=5)
        tk.Label(srow2, text=T('lbl_duration')).pack(side='left', padx=(10, 0))
        self.bp_duration_var = tk.StringVar(value=settings.get('bp_duration', settings.get('audio_sync_duration', "120")))
        tk.Entry(srow2, textvariable=self.bp_duration_var, width=5).pack(side='left', padx=5)
        tk.Label(srow2, text=T('lbl_batch_start')).pack(side='left', padx=(10, 0))
        self.bp_start_var = tk.StringVar(value=settings.get('bp_start', settings.get('audio_sync_start', "300")))
        tk.Entry(srow2, textvariable=self.bp_start_var, width=5).pack(side='left', padx=5)

        out_row = tk.Frame(sec4)
        out_row.pack(fill='x', pady=1)
        self.bp_output_dir_var = tk.BooleanVar(value=settings.get('bp_output_dir', False))
        ttk.Checkbutton(out_row, text="Dossier de sortie :",
                        variable=self.bp_output_dir_var).pack(side='left')
        self.bp_output_path_var = tk.StringVar(value=settings.get('bp_output_path', ''))
        tk.Entry(out_row, textvariable=self.bp_output_path_var, width=30).pack(
            side='left', padx=4, fill='x', expand=True)
        tk.Button(out_row, text="📁", command=self._browse_output_dir,
                  bg='#e1e1e1').pack(side='left', padx=2)
        tk.Label(out_row, text="(vide = sous-dossier auto)",
                 fg='gray', font=("Arial", 8, "italic")).pack(side='left', padx=4)

        self.bp_run_btn = tk.Button(sec4, text=T('bp_run'), command=self._run_pipeline,
                                    bg='#008000', fg='white', font=("Arial", 11, "bold"))
        self.bp_run_btn.pack(fill='x', pady=4)

        self.bp_progress = ttk.Progressbar(sec4, orient='horizontal', mode='determinate')
        self.bp_progress.pack(fill='x', pady=1)

        self.bp_status_lbl = tk.Label(sec4, text="", fg='#0066cc',
                                      font=("Arial", 9, "bold"), anchor='w')
        self.bp_status_lbl.pack(fill='x', pady=1)

        self.bp_log = scrolledtext.ScrolledText(sec4, height=6)
        self.bp_log.pack(fill='both', expand=True, pady=2)

    # ---- File management ----
    def _drop_files(self, event):
        for f in self.winfo_toplevel().tk.splitlist(event.data):
            if f.lower().endswith('.mkv'):
                self.file_list.insert(tk.END, f)

    def _add_files(self):
        for f in filedialog.askopenfilenames(filetypes=[("MKV Files", "*.mkv")]):
            self.file_list.insert(tk.END, f)

    def _add_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            for f in glob.glob(os.path.join(folder, "**/*.mkv"), recursive=True):
                self.file_list.insert(tk.END, f)

    def _remove_selected(self):
        for i in self.file_list.curselection()[::-1]:
            self.file_list.delete(i)

    def _clear_files(self):
        self.file_list.delete(0, tk.END)
        self.rename_tree.delete(*self.rename_tree.get_children())
        self.file_results.clear()

    def _bp_log(self, txt):
        self.after(0, lambda: (self.bp_log.insert(tk.END, txt + "\n"), self.bp_log.see(tk.END)))

    # ---- PanedWindow size persistence ----
    def _init_pane_sizes(self):
        """Set initial pane heights (as proportions of total) after window renders."""
        if self._pane_init_done:
            return
        total = self.bp_paned.winfo_height()
        if total < 50:
            # Not rendered yet, retry
            self.after(200, self._init_pane_sizes)
            return
        saved = self.settings.get('bp_pane_sizes')
        # Saved as proportions [0.0-1.0] of total height
        if saved and len(saved) == 3 and all(0 < p < 1 for p in saved):
            positions = [max(60, int(p * total)) for p in saved]
        else:
            # Defaults: sec1=15%, sec2=37%, sec3=57% of total
            positions = [int(total * 0.15), int(total * 0.37), int(total * 0.57)]
        try:
            for i, y in enumerate(positions):
                self.bp_paned.sash_place(i, 1, y)
            self._pane_init_done = True
        except Exception as e:
            logger.debug(f"PanedWindow sash init: {e}")

    def _get_pane_sizes(self):
        """Return sash positions as proportions of total height (portable across window sizes)."""
        try:
            total = self.bp_paned.winfo_height()
            if total < 50:
                return None
            return [self.bp_paned.sash_coord(i)[1] / total for i in range(3)]
        except Exception:
            return None

    # ---- Meta picker ----
    def _open_meta_picker(self):
        """Open MetadataPickerDialog for the selected (or first) file."""
        sel = self.rename_tree.selection()
        fp = sel[0] if sel else (list(self.file_results.keys())[0] if self.file_results else None)
        if not fp:
            messagebox.showwarning("Batch Pro",
                                   "Aucun résultat — lancez d'abord 🔍 Rechercher les noms.")
            return
        lang = self.search_lang_var.get()
        lang_tvdb = {'fr': 'fra', 'en': 'eng', 'ja': 'jpn', 'de': 'deu',
                     'es': 'spa', 'it': 'ita'}.get(lang, 'eng')
        lang_tmdb = {'fr': 'fr-FR', 'en': 'en-US', 'ja': 'ja-JP', 'de': 'de-DE',
                     'es': 'es-ES', 'it': 'it-IT'}.get(lang, 'en-US')
        MetadataPickerDialog(self.winfo_toplevel(), fp,
                             self.file_results, self.settings, lang_tvdb, lang_tmdb,
                             batch_pro_tab=self)

    # ---- Auto-rename ----
    def _get_resolver(self):
        tvdb = self.settings.get('tvdb_api_key', '')
        tmdb = self.settings.get('tmdb_api_key', '')
        lang = self.search_lang_var.get()
        provider_choice = self.bp_api_var.get()
        lang_tvdb = {'fr': 'fra', 'en': 'eng', 'ja': 'jpn', 'de': 'deu',
                     'es': 'spa', 'it': 'ita'}.get(lang, 'eng')
        lang_tmdb = {'fr': 'fr-FR', 'en': 'en-US', 'ja': 'ja-JP', 'de': 'de-DE',
                     'es': 'es-ES', 'it': 'it-IT'}.get(lang, 'en-US')
        if provider_choice == 'TVDB':
            return MetadataResolver(tvdb, '', lang_tvdb, lang_tmdb, include_tvmaze=False)
        elif provider_choice == 'TMDB':
            return MetadataResolver('', tmdb, lang_tvdb, lang_tmdb, include_tvmaze=False)
        elif provider_choice == 'TVmaze':
            return MetadataResolver('', '', lang_tvdb, lang_tmdb, include_tvmaze=True)
        else:  # Auto
            return MetadataResolver(tvdb, tmdb, lang_tvdb, lang_tmdb, include_tvmaze=True)

    def _search_names(self):
        files = list(self.file_list.get(0, tk.END))
        if not files:
            messagebox.showwarning("Batch Pro", "Aucun fichier ajouté !")
            return
        if not self.settings.get('tvdb_api_key') and not self.settings.get('tmdb_api_key'):
            self._bp_log(T('bp_no_apikey'))
        self.bp_search_status.config(text=T('bp_searching'))
        threading.Thread(target=self._search_names_worker, args=(files,), daemon=True).start()

    def _search_names_worker(self, files):
        resolver = self._get_resolver()
        # Also build resolvers for each individual provider (for picker multi-source)
        tvdb_key = self.settings.get('tvdb_api_key', '')
        tmdb_key = self.settings.get('tmdb_api_key', '')
        lang = self.search_lang_var.get()
        lang_tvdb = {'fr': 'fra', 'en': 'eng', 'ja': 'jpn', 'de': 'deu',
                     'es': 'spa', 'it': 'ita'}.get(lang, 'eng')
        lang_tmdb = {'fr': 'fr-FR', 'en': 'en-US', 'ja': 'ja-JP', 'de': 'de-DE',
                     'es': 'es-ES', 'it': 'it-IT'}.get(lang, 'en-US')
        per_provider = {}
        if tvdb_key:
            per_provider['TVDB'] = MetadataResolver(tvdb_key, '', lang_tvdb, lang_tmdb, include_tvmaze=False)
        if tmdb_key:
            per_provider['TMDB'] = MetadataResolver('', tmdb_key, lang_tvdb, lang_tmdb, include_tvmaze=False)
        per_provider['TVmaze'] = MetadataResolver('', '', lang_tvdb, lang_tmdb, include_tvmaze=True)

        mkvmerge = self.parent_app.mkvmerge_path_entry.get()
        ffprobe = self.settings.get('ffprobe_path', find_ffprobe())

        self.after(0, lambda: self.rename_tree.delete(*self.rename_tree.get_children()))
        self.file_results.clear()

        for f in files:
            parsed = parse_media_filename(f)
            meta = detect_video_metadata(f, mkvmerge, ffprobe)
            chosen = {}
            status = '?'
            # Search each provider independently (for picker)
            all_provider_results = {}
            for pname, presolver in per_provider.items():
                try:
                    if parsed['kind'] == 'series':
                        results = presolver.search_series(parsed['title'])
                    else:
                        results = presolver.search_movie(parsed['title'], parsed.get('year')) if any(
                            hasattr(p, 'search_movie') for _, p in presolver.providers) else []
                    if results:
                        all_provider_results[pname] = results[0]
                except Exception as e:
                    logger.debug(f"Search {pname} failed: {e}")
            try:
                embed_meta = self.bp_embed_meta_var.get()
                if parsed['kind'] == 'series':
                    matches = resolver.search_series(parsed['title'])
                    if matches:
                        chosen = dict(matches[0])
                        if embed_meta:
                            ep_meta = resolver.resolve_full_episode(
                                chosen['provider'], chosen['id'],
                                parsed['season'], parsed['episode'])
                            if ep_meta.get('name'):
                                chosen['episode_name'] = ep_meta['name']
                            chosen['description'] = ep_meta.get('description', '')
                            chosen['cover_url'] = ep_meta.get('poster_url') or ep_meta.get('still_url', '')
                            # Copy ALL enriched fields to chosen
                            for _k in ('genres', 'cast', 'imdb_id', 'content_rating', 'aired'):
                                if ep_meta.get(_k):
                                    chosen[_k] = ep_meta[_k]
                        else:
                            ep_name = resolver.resolve_episode(
                                chosen['provider'], chosen['id'],
                                parsed['season'], parsed['episode'])
                            if ep_name:
                                chosen['episode_name'] = ep_name
                        status = f"✓ {chosen.get('provider', '?')}"
                else:
                    matches = resolver.search_movie(parsed['title'], parsed.get('year'))
                    if matches:
                        chosen = dict(matches[0])
                        if embed_meta:
                            mv_meta = resolver.resolve_movie_meta(chosen['provider'], chosen['id'])
                            chosen['description'] = mv_meta.get('description', '')
                            chosen['cover_url'] = mv_meta.get('poster_url', '')
                            for _k in ('genres', 'cast', 'imdb_id', 'content_rating', 'aired'):
                                if mv_meta.get(_k):
                                    chosen[_k] = mv_meta[_k]
                        status = f"✓ {chosen.get('provider', '?')}"
            except Exception as e:
                logger.debug(f"Search failed for {f}: {e}")
                matches = []

            ext = os.path.splitext(f)[1]
            newname = build_output_filename(parsed, chosen, meta, ext) if chosen else os.path.basename(f)
            detected = f"{parsed['kind']}"
            if parsed['kind'] == 'series':
                detected += f" S{parsed['season']:02d}E{parsed['episode']:02d}"
            elif parsed.get('year'):
                detected += f" ({parsed['year']})"

            self.file_results[f] = {
                'parsed': parsed, 'meta': meta, 'matches': matches,
                'chosen': chosen, 'newname': newname,
                'all_provider_results': all_provider_results,
            }
            self.after(0, lambda ff=f, d=detected, nn=newname, st=status:
                       self.rename_tree.insert('', 'end', iid=ff,
                                               values=(os.path.basename(ff), d, nn, st)))

        self.after(0, lambda: self.bp_search_status.config(text=T('bp_search_done')))

    def _on_rename_edit(self, event):
        """Double-click to edit the new name cell inline."""
        item = self.rename_tree.identify_row(event.y)
        col = self.rename_tree.identify_column(event.x)
        if not item or col != '#3':  # newname column
            return
        x, y, w, h = self.rename_tree.bbox(item, col)
        cur = self.rename_tree.set(item, 'newname')
        entry = tk.Entry(self.rename_tree)
        entry.insert(0, cur)
        entry.select_range(0, tk.END)
        entry.focus()
        entry.place(x=x, y=y, width=w, height=h)

        def _commit(_e=None):
            val = entry.get()
            self.rename_tree.set(item, 'newname', val)
            if item in self.file_results:
                self.file_results[item]['newname'] = val
            entry.destroy()

        entry.bind('<Return>', _commit)
        entry.bind('<FocusOut>', _commit)
        entry.bind('<Escape>', lambda e: entry.destroy())

    # ---- Track order ----
    def _load_full_tracks(self, mkv_path):
        """Load all tracks (incl. video) with forced flag for reorder matching."""
        mkvmerge = self.parent_app.mkvmerge_path_entry.get()
        try:
            res = run_hidden([mkvmerge, "-J", mkv_path])
            info = json.loads(res.stdout)
            tracks = []
            for t in info.get("tracks", []):
                props = t.get("properties", {})
                tracks.append({
                    'id': t['id'],
                    'type': t['type'],
                    'codec': _normalize_codec(props.get('codec_id', ''), t.get('codec', '')),
                    'lang': props.get('language', 'und'),
                    'name': props.get('track_name', ''),
                    'forced': bool(props.get('forced_track', False)),
                    'default': bool(props.get('default_track', False)),
                })
            return tracks
        except Exception as e:
            logger.error(f"Full track load failed: {e}")
            return []

    def _browse_output_dir(self):
        d = filedialog.askdirectory(title="Dossier de sortie")
        if d:
            self.bp_output_path_var.set(d)

    def _load_first_file_ref_tracks(self):
        files = list(self.file_list.get(0, tk.END))
        if not files:
            messagebox.showwarning("Batch Pro", "Aucun fichier dans la liste !")
            return
        tracks = self._load_full_tracks(files[0])
        self.track_tree.delete(*self.track_tree.get_children())
        for t in tracks:
            self.track_tree.insert('', 'end', iid=str(t['id']),
                                   values=(t['id'], t['type'], t.get('codec', ''), t['lang'], t['name'],
                                           '✓' if t['forced'] else '',
                                           '✓' if t.get('default') else ''))

    def _load_ref_tracks(self):
        f = filedialog.askopenfilename(filetypes=[("MKV Files", "*.mkv")])
        if not f:
            return
        tracks = self._load_full_tracks(f)
        self.track_tree.delete(*self.track_tree.get_children())
        for t in tracks:
            self.track_tree.insert('', 'end', iid=str(t['id']),
                                   values=(t['id'], t['type'], t.get('codec', ''), t['lang'], t['name'],
                                           '✓' if t['forced'] else '',
                                           '✓' if t.get('default') else ''))

    def _move_track(self, direction):
        sel = self.track_tree.selection()
        if not sel:
            return
        item = sel[0]
        idx = self.track_tree.index(item)
        new_idx = idx + direction
        children = self.track_tree.get_children()
        if 0 <= new_idx < len(children):
            self.track_tree.move(item, '', new_idx)

    def _build_track_template(self):
        """Read the current track_tree order into a matching template."""
        template = []
        for item in self.track_tree.get_children():
            vals = self.track_tree.item(item, 'values')
            template.append({
                'type': vals[1],
                'lang': vals[3],
                'forced': vals[5] == '✓',
            })
        return template

    def _compute_track_order(self, file_tracks, template):
        """Match file tracks to template order.
        Returns (ordered_ids, unmatched_tmpl, extra_tracks).
        unmatched_tmpl = template entries absent from this file.
        extra_tracks   = file tracks not in template (appended at end).
        """
        used = set()
        ordered_ids = []
        unmatched_tmpl = []
        for tmpl in template:
            matched = False
            for t in file_tracks:
                if t['id'] in used:
                    continue
                if (t['type'] == tmpl['type'] and t['lang'] == tmpl['lang']
                        and t['forced'] == tmpl['forced']):
                    ordered_ids.append(t['id'])
                    used.add(t['id'])
                    matched = True
                    break
            if not matched:
                unmatched_tmpl.append(tmpl)
        # Append any unmatched file tracks in original order
        extra_tracks = []
        for t in file_tracks:
            if t['id'] not in used:
                ordered_ids.append(t['id'])
                used.add(t['id'])
                extra_tracks.append(t)
        return ordered_ids, unmatched_tmpl, extra_tracks

    # ---- Metadata embedding ----
    def _apply_picker_prefs(self, filepath, chosen, prefs):
        """Fetch per-file content from picker source preferences.
        Cover = series poster (same for all episodes).
        Description/synopsis = per-episode content from chosen provider.
        """
        res = self.file_results.get(filepath, {})
        all_pr = res.get('all_provider_results', {})
        parsed = res.get('parsed', {})
        tvdb_key = self.settings.get('tvdb_api_key', '')
        tmdb_key = self.settings.get('tmdb_api_key', '')
        lang = self.search_lang_var.get()
        lang_tvdb = {'fr': 'fra', 'en': 'eng', 'ja': 'jpn', 'de': 'deu',
                     'es': 'spa', 'it': 'ita'}.get(lang, 'eng')
        lang_tmdb = {'fr': 'fr-FR', 'en': 'en-US', 'ja': 'ja-JP', 'de': 'de-DE',
                     'es': 'es-ES', 'it': 'it-IT'}.get(lang, 'en-US')

        def _get_provider(pname):
            if pname == 'TVDB' and tvdb_key:
                return TVDBProvider(tvdb_key, lang_tvdb)
            if pname == 'TMDB' and tmdb_key:
                return TMDBProvider(tmdb_key, lang_tmdb)
            if pname == 'TVmaze':
                return TVmazeProvider()
            return None

        cover_src = prefs.get('cover_src', '')
        desc_src = prefs.get('desc_src', '')
        syn_src = prefs.get('synopsis_src', '')
        cast_src = prefs.get('cast_src', '')
        genre_src = prefs.get('genre_src', '')
        crew_src = prefs.get('crew_src', '')
        crew_markers = ('__director__', '__writer__', '__producer__', '__studio__')

        def _fetch_cast(pname):
            if not pname or pname not in all_pr:
                return []
            try:
                prov = _get_provider(pname)
                sid = all_pr[pname]['id']
                if not prov or parsed.get('kind') != 'series':
                    if prov and hasattr(prov, 'get_episode_cast') and parsed.get('kind') == 'series':
                        pass
                    else:
                        return []
                if hasattr(prov, 'get_episode_cast'):
                    return prov.get_episode_cast(sid, parsed['season'], parsed['episode'])
            except Exception as e:
                logger.debug(f"Prefs _fetch_cast {pname}: {e}")
            return []

        if cover_src and cover_src in all_pr:
            try:
                prov = _get_provider(cover_src)
                sid = all_pr[cover_src]['id']
                if prov and hasattr(prov, 'get_series_poster'):
                    url = prov.get_series_poster(sid)
                    if url:
                        chosen['cover_url'] = url
                elif prov and parsed.get('kind') == 'series':
                    ep_meta = prov.get_episode_meta(sid, parsed['season'], parsed['episode'])
                    chosen['cover_url'] = ep_meta.get('still_url', '')
            except Exception as e:
                logger.debug(f"Prefs cover fetch: {e}")

        # Cast (actors from cast_src) + crew (director/producer from crew_src), merged
        merged_cast = []
        if cast_src:
            merged_cast += [a for a in _fetch_cast(cast_src) if a.get('role') not in crew_markers]
        if crew_src:
            merged_cast += [a for a in _fetch_cast(crew_src) if a.get('role') in crew_markers]
        if merged_cast:
            chosen['cast'] = merged_cast

        # Genres from series meta
        if genre_src and genre_src in all_pr:
            try:
                prov = _get_provider(genre_src)
                sid = all_pr[genre_src]['id']
                if prov and hasattr(prov, 'get_series_meta'):
                    s_meta = prov.get_series_meta(sid)
                    if s_meta.get('genres'):
                        chosen['genres'] = s_meta['genres']
            except Exception as e:
                logger.debug(f"Prefs genres fetch: {e}")

        for src_key, chosen_key in [(desc_src, 'description'), (syn_src, 'synopsis')]:
            if src_key and src_key in all_pr:
                try:
                    prov = _get_provider(src_key)
                    sid = all_pr[src_key]['id']
                    if prov:
                        if parsed.get('kind') == 'series':
                            ep_meta = prov.get_episode_meta(sid, parsed['season'], parsed['episode'])
                        else:
                            ep_meta = prov.get_movie_meta(sid) if hasattr(prov, 'get_movie_meta') else {}
                        text = ep_meta.get('description', '')
                        if text:
                            chosen[chosen_key] = text
                except Exception as e:
                    logger.debug(f"Prefs {chosen_key} fetch: {e}")

        return chosen

    def _generate_kodi_nfo(self, parsed, chosen, series_title=''):
        """Generate Kodi-compatible NFO XML string (episodedetails or movie)."""
        ep_title = xml_safe_text(chosen.get('episode_name') or chosen.get('name') or '')
        description = xml_safe_text(chosen.get('description') or '')
        synopsis = xml_safe_text(chosen.get('synopsis') or description)
        aired = xml_safe_text(chosen.get('aired') or '')
        year = chosen.get('year', '') or parsed.get('year', '')
        genres = chosen.get('genres') or []
        cast = chosen.get('cast') or []
        imdb_id = xml_safe_text(chosen.get('imdb_id') or '')
        content_rating = xml_safe_text(chosen.get('content_rating') or '')

        if parsed.get('kind') == 'series':
            root = ET.Element('episodedetails')
            ET.SubElement(root, 'title').text = ep_title
            ET.SubElement(root, 'showtitle').text = series_title or chosen.get('name', '')
            if parsed.get('season'):
                ET.SubElement(root, 'season').text = str(parsed['season'])
            if parsed.get('episode'):
                ET.SubElement(root, 'episode').text = str(parsed['episode'])
            ET.SubElement(root, 'plot').text = synopsis
            ET.SubElement(root, 'outline').text = description
            if aired:
                ET.SubElement(root, 'aired').text = aired
            elif year:
                ET.SubElement(root, 'aired').text = str(year)
        else:
            root = ET.Element('movie')
            ET.SubElement(root, 'title').text = ep_title or chosen.get('name', '')
            ET.SubElement(root, 'plot').text = synopsis
            ET.SubElement(root, 'outline').text = description
            if year:
                ET.SubElement(root, 'year').text = str(year)

        # Director + producers + studios (from crew markers)
        directors_nfo = [a['name'] for a in cast if a.get('role') == '__director__']
        producers_nfo = [a['name'] for a in cast if a.get('role') == '__producer__']
        studios_nfo = [a['name'] for a in cast if a.get('role') == '__studio__']
        actors_nfo = [a for a in cast if a.get('role') not in
                      ('__director__', '__writer__', '__producer__', '__studio__')]
        for d in directors_nfo:
            ET.SubElement(root, 'director').text = d
        for p in producers_nfo:
            ET.SubElement(root, 'producer').text = p
        for st in studios_nfo:
            ET.SubElement(root, 'studio').text = st

        # Common fields
        cast = actors_nfo
        for genre in genres:
            if genre:
                ET.SubElement(root, 'genre').text = genre
        if content_rating:
            ET.SubElement(root, 'mpaa').text = content_rating
        if imdb_id:
            uid = ET.SubElement(root, 'uniqueid')
            uid.set('type', 'imdb')
            uid.set('default', 'true')
            uid.text = imdb_id
        for actor in cast[:15]:
            aname = actor.get('name', '')
            if not aname:
                continue
            a_el = ET.SubElement(root, 'actor')
            ET.SubElement(a_el, 'name').text = aname
            if actor.get('role'):
                ET.SubElement(a_el, 'role').text = actor['role']

        if not ep_title and not description and not genres:
            return None  # nothing meaningful to embed
        body = _XML_INVALID_RE.sub('', ET.tostring(root, encoding='unicode'))
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + body)

    def _embed_metadata_to_file(self, mkv_path, chosen, parsed):
        """Embed MKV tags, cover art and Kodi NFO via mkvpropedit (restored f60b167 flow)."""
        mkvpropedit = self.parent_app.mkvpropedit_path_entry.get()
        if not mkvpropedit or not os.path.exists(mkvpropedit):
            self._bp_log("  ⚠️ embed meta: mkvpropedit introuvable")
            return

        # Pre-pass: delete old attachments in a SEPARATE call (as in the working
        # f60b167 release). Combining delete + add in one call broke some files.
        if chosen.get('clean_tags', True):
            del_args = [mkvpropedit, mkv_path]
            for att_name in ('cover.jpg', 'cover.png', 'cover.jpeg', 'kodi-metadata'):
                del_args += ['--delete-attachment', f'name:{att_name}']
            try:
                run_hidden(del_args)  # return code ignored (attachment may be absent)
                self._bp_log("  meta: anciens attachments supprimés")
            except Exception:
                pass

        temp_files = []
        try:
            # ── Parse chosen fields (guard against None) ──────────────────────
            title = (chosen.get('episode_name') or chosen.get('name') or '').strip()
            series_title = (chosen.get('name') or '') if parsed.get('kind') == 'series' else ''
            description = (chosen.get('description') or '').strip()
            synopsis = (chosen.get('synopsis') or description).strip()
            aired = (chosen.get('aired') or '').strip()
            year = (chosen.get('year') or parsed.get('year') or '')
            date_str = aired or (str(year) if year else '')
            genres = chosen.get('genres') or []
            cast = chosen.get('cast') or []
            imdb_id = (chosen.get('imdb_id') or '').strip()
            content_rating = (chosen.get('content_rating') or '').strip()
            cover_url = (chosen.get('cover_url') or '').strip()

            # ── Main embed call: tags + cover + kodi (NO --edit info) ─────────
            args = [mkvpropedit, mkv_path]

            # 2. Build XML tags + add --tags + --edit info --set title
            if title or description or synopsis or genres or cast:
                root = ET.Element('Tags')
                tag_el = ET.SubElement(root, 'Tag')
                targets = ET.SubElement(tag_el, 'Targets')
                ET.SubElement(targets, 'TargetTypeValue').text = '50'
                # CRITICAL: add a TargetType string. mkvpropedit strips TargetTypeValue=50
                # (the default value), leaving <Targets/> empty — which makes MediaInfo/VLC
                # IGNORE all global tags. The TargetType string is never stripped, so Targets
                # stays non-empty and players read the tags. Without this, tags are written
                # but invisible in MediaInfo (the long-standing "tags missing" bug).
                ET.SubElement(targets, 'TargetType').text = 'MOVIE'
                def _simple(name, value):
                    val = xml_safe_text(value)
                    if not val:
                        return
                    s = ET.SubElement(tag_el, 'Simple')
                    ET.SubElement(s, 'Name').text = name
                    ET.SubElement(s, 'String').text = val
                if title:
                    _simple('TITLE', title)
                if description:
                    _simple('SUMMARY', description)
                    _simple('DESCRIPTION', description)
                if synopsis and synopsis != description:
                    _simple('SYNOPSIS', synopsis)
                if date_str:
                    _simple('DATE_RELEASED', date_str)
                if series_title:
                    _simple('SHOW', series_title)
                _simple('CONTENT_TYPE', 'TV Show' if parsed.get('kind') == 'series' else 'Movie')
                if parsed.get('kind') == 'series':
                    if parsed.get('season'):
                        _simple('SEASON.PART_NUM', str(parsed['season']))
                    if parsed.get('episode'):
                        _simple('EPISODE.PART_NUM', str(parsed['episode']))
                directors = [a['name'] for a in cast if a.get('role') == '__director__']
                writers   = [a['name'] for a in cast if a.get('role') == '__writer__']
                producers = [a['name'] for a in cast if a.get('role') == '__producer__']
                studios   = [a['name'] for a in cast if a.get('role') == '__studio__']
                actors_only = [a for a in cast if a.get('role') not in
                               ('__director__', '__writer__', '__producer__', '__studio__')]
                if directors:
                    _simple('DIRECTOR', ', '.join(directors))
                if writers:
                    _simple('WRITTEN_BY', ', '.join(writers))
                if producers:
                    _simple('PRODUCER', ', '.join(producers))
                if studios:
                    studio_str = ', '.join(studios)
                    _simple('PRODUCTION_STUDIO', studio_str)
                    _simple('COPYRIGHT', studio_str)
                if actors_only:
                    artist_str = ', '.join(a['name'] for a in actors_only[:10] if a.get('name'))
                    if artist_str:
                        _simple('ARTIST', artist_str)
                        _simple('ACTOR', artist_str)
                if genres:
                    _simple('GENRE', ', '.join(g for g in genres if g))
                if content_rating:
                    _simple('LAW_RATING', content_rating)
                    _simple('RATING', content_rating)
                if imdb_id:
                    _simple('IMDB', imdb_id)

                xml_body = _XML_INVALID_RE.sub('', ET.tostring(root, encoding='unicode'))
                xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body
                tf = tempfile.NamedTemporaryFile(suffix='.xml', delete=False, mode='w', encoding='utf-8')
                tf.write(xml_str)
                tf.close()
                temp_files.append(tf.name)
                args += ['--tags', f'all:{tf.name}']
                logger.debug(f"BatchPro embed tags XML ({len(xml_str)} chars) for {os.path.basename(mkv_path)}")
                self._bp_log(f"  meta: tags title={title[:40]!r} desc={len(description)}c "
                             f"genres={genres[:2]} cover={'✓' if cover_url else '✗'}")

            # 3. Cover art download → add attachment in same call
            if cover_url:
                try:
                    ext = '.png' if cover_url.lower().endswith('.png') else '.jpg'
                    mime = 'image/png' if ext == '.png' else 'image/jpeg'
                    cf = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
                    cf.close()
                    req = urllib.request.Request(cover_url, headers={'User-Agent': 'PyMkvPropEdit/3.7'})
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        with open(cf.name, 'wb') as fout:
                            fout.write(resp.read())
                    temp_files.append(cf.name)
                    args += ['--attachment-name', f'cover{ext}',
                             '--attachment-mime-type', mime,
                             '--add-attachment', cf.name]
                    self._bp_log("  meta: cover art téléchargé")
                except Exception as e:
                    self._bp_log(f"  ⚠️ meta: cover download échoué: {e}")

            # 4. Kodi NFO → add attachment in same call
            try:
                nfo_xml = self._generate_kodi_nfo(parsed, chosen, series_title)
                if nfo_xml:
                    nf = tempfile.NamedTemporaryFile(suffix='.nfo', delete=False, mode='w', encoding='utf-8')
                    nf.write(nfo_xml)
                    nf.close()
                    temp_files.append(nf.name)
                    args += ['--attachment-name', 'kodi-metadata',
                             '--attachment-mime-type', 'application/xml',
                             '--add-attachment', nf.name]
                    self._bp_log("  meta: kodi-metadata NFO généré")
            except Exception as e:
                self._bp_log(f"  ⚠️ meta: kodi-metadata échoué: {e}")

            # ── ONE mkvpropedit call for everything ───────────────────────────
            if len(args) > 2:
                proc = run_hidden(args)
                logger.debug(f"BatchPro embed mkvpropedit RC={proc.returncode}")
                if proc.stderr:
                    logger.debug(f"BatchPro embed stderr: {proc.stderr}")
                if proc.returncode in (0, 1):
                    self._bp_log("  meta: intégrée OK")
                else:
                    self._bp_log(f"  ⚠️ meta: mkvpropedit code {proc.returncode} — stderr: {proc.stderr[:200] if proc.stderr else ''}")
            else:
                self._bp_log("  ⚠️ meta: aucun tag/attachment à écrire (args vides)")
        finally:
            for f in temp_files:
                safe_remove(f)

    # ---- Pipeline execution ----
    def _run_pipeline(self):
        files = list(self.file_list.get(0, tk.END))
        if not files:
            messagebox.showwarning("Batch Pro", "Aucun fichier ajouté !")
            return
        self.bp_run_btn.config(state='disabled')
        self.bp_progress['maximum'] = len(files)
        self.bp_progress['value'] = 0
        self.bp_status_lbl.config(text=f"Démarrage… 0/{len(files)} (0%)", fg='#0066cc')
        self.bp_log.delete("1.0", tk.END)
        threading.Thread(target=self._pipeline_worker, args=(files,), daemon=True).start()

    def _pipeline_worker(self, files):
        do_sync = self.bp_sync_var.get()
        do_sync_subs = self.bp_sync_subs_var.get()
        do_props = self.bp_props_var.get()
        do_reorder = self.bp_reorder_var.get()
        do_rename = self.bp_rename_var.get()
        preserve_src = self.bp_preserve_src_var.get()
        use_output_dir = self.bp_output_dir_var.get()
        output_dir_path = self.bp_output_path_var.get().strip()
        mkvmerge = self.parent_app.mkvmerge_path_entry.get()
        ref_lang = self.bp_ref_lang_var.get().split()[0]
        try:
            duration = int(self.bp_duration_var.get())
        except ValueError:
            duration = 120
        try:
            start_offset = int(self.bp_start_var.get())
        except ValueError:
            start_offset = 300

        template = self._build_track_template() if do_reorder else []
        start_time = time.time()
        done = 0

        for mkv_path in files:
            base_name = os.path.basename(mkv_path)
            self._bp_log(f"━━ {base_name} ━━")
            try:
                # Safety guard: skip immediately if source file no longer exists
                if not os.path.exists(mkv_path):
                    self._bp_log(f"  ⛔ fichier source introuvable (déjà déplacé/renommé ?): {mkv_path}")
                    self._bp_log(f"  ✗ ignoré")
                    done += 1
                    continue

                current_file = mkv_path
                needs_remux = False
                sync_flags = []
                order_arg = []

                # Compute sync delays
                if do_sync:
                    tracks_data = self.load_mkv_tracks(mkv_path, mkvmerge)
                    if tracks_data:
                        ref_track = next((t for t in tracks_data if t["type"] == "audio"
                                          and t["lang"] == ref_lang), None)
                        if not ref_track:
                            ref_track = next((t for t in tracks_data if t["type"] == "audio"), None)
                        if ref_track:
                            ref_data = self.extract_audio_track(
                                mkv_path, ref_track["ffmpeg_idx"], duration,
                                self.temp_files, start_offset)
                            if ref_data is not None:
                                for t in tracks_data:
                                    if t["type"] == "audio" and t["id"] != ref_track["id"]:
                                        td = self.extract_audio_track(
                                            mkv_path, t["ffmpeg_idx"], duration,
                                            self.temp_files, start_offset)
                                        if td is not None:
                                            t["delay"] = self.calculate_delay(ref_data, td)
                                            t["processed"] = True
                                # Apply to subtitles same lang (if checkbox checked)
                                if do_sync_subs:
                                    lang_delays = {t["lang"]: t["delay"] for t in tracks_data
                                                   if t["type"] == "audio" and t.get("processed")}
                                    for t in tracks_data:
                                        if t["type"] == "subtitles" and t["lang"] in lang_delays:
                                            t["delay"] = lang_delays[t["lang"]]
                                            t["processed"] = True
                                for t in tracks_data:
                                    if t.get("processed") and t["delay"] != 0:
                                        sync_flags += ["--sync", f"{t['id']}:{t['delay']}"]
                                        sign = "+" if t["delay"] > 0 else ""
                                        tname_str = f" [{t['name']}]" if t.get('name') else ""
                                        self._bp_log(f"  sync trk{t['id']} {t['type']}/{t['lang']}{tname_str}: {sign}{t['delay']}ms")
                                if not sync_flags:
                                    self._bp_log("  sync: aucun décalage détecté (pistes déjà en phase)")
                    if sync_flags:
                        needs_remux = True

                # Compute reorder
                if do_reorder and template:
                    file_tracks = self._load_full_tracks(mkv_path)
                    ordered_ids, unmatched_tmpl, extra_tracks = self._compute_track_order(file_tracks, template)
                    if unmatched_tmpl:
                        desc = ", ".join(f"{t['type']}/{t['lang']}" for t in unmatched_tmpl)
                        self._bp_log(f"  ⚠️ pistes template absentes de ce fichier: {desc}")
                    if extra_tracks:
                        desc = ", ".join(f"{t['type']}/{t['lang']}" for t in extra_tracks)
                        self._bp_log(f"  ℹ️ pistes hors template ajoutées en fin: {desc}")
                    # Only remux if order actually differs
                    if ordered_ids != [t['id'] for t in file_tracks]:
                        order_str = ",".join(f"0:{tid}" for tid in ordered_ids)
                        order_arg = ["--track-order", order_str]
                        needs_remux = True
                        self._bp_log(f"  réordonnancement: {order_str}")
                    else:
                        self._bp_log("  ordre pistes: déjà correct, pas de remux nécessaire")

                # Preserve source: if no remux planned but user wants source kept,
                # create a fast copy so we process the copy and leave source intact.
                if preserve_src and not needs_remux:
                    b, ext = os.path.splitext(mkv_path)
                    out_file = f"{b}_COPY{ext}"
                    # Use mkvmerge (not shutil.copy2) so the output is a clean MKV
                    # that mkvpropedit can always modify in-place without errors
                    proc_copy = run_hidden([mkvmerge, "-o", out_file, mkv_path])
                    if proc_copy.returncode in (0, 1) and os.path.exists(out_file):
                        current_file = out_file
                        self._bp_log("  source préservée → copie propre créée")
                    else:
                        self._bp_log(f"  ⚠️ copie source échouée (code {proc_copy.returncode}), traitement en place")

                # Single-pass mkvmerge (sync + reorder)
                if needs_remux:
                    b, ext = os.path.splitext(mkv_path)
                    out_file = f"{b}_PRO{ext}"
                    cmd = [mkvmerge, "-o", out_file] + sync_flags + order_arg + [mkv_path]
                    proc = run_hidden(cmd)
                    if proc.returncode in (0, 1) and os.path.exists(out_file):
                        current_file = out_file
                        self._bp_log("  remux OK")
                    else:
                        self._bp_log(f"  ⚠️ remux échec (code {proc.returncode})")

                # mkvpropedit params
                if do_props:
                    success, msg = self.apply_mkvpropedit_to_file(current_file, self.parent_app)
                    self._bp_log(f"  mkvpropedit: {msg or 'OK'}")

                # Embed metadata (tags + cover art)
                do_embed = self.bp_embed_meta_var.get()
                if do_embed and mkv_path in self.file_results:
                    res = self.file_results[mkv_path]
                    chosen_embed = dict(res.get('chosen', {}))
                    chosen_embed['clean_tags'] = self.bp_clean_tags_var.get()
                    # If picker prefs exist, re-fetch per-episode content from chosen provider
                    prefs = self.meta_picker_prefs
                    if prefs:
                        chosen_embed = self._apply_picker_prefs(mkv_path, chosen_embed, prefs)
                    if chosen_embed.get('description') or chosen_embed.get('cover_url'):
                        self._embed_metadata_to_file(current_file, chosen_embed, res.get('parsed', {}))
                    else:
                        self._bp_log("  meta: pas de données (lancer 🔍 d'abord)")

                # Finalize: rename + optional output directory
                final_name = os.path.basename(current_file)
                if do_rename and mkv_path in self.file_results:
                    proposed = self.file_results[mkv_path].get('newname', '')
                    if proposed:
                        final_name = proposed

                # Determine final directory
                if use_output_dir:
                    final_dir = output_dir_path if output_dir_path else os.path.join(
                        os.path.dirname(mkv_path), "Batch Pro Output")
                    try:
                        os.makedirs(final_dir, exist_ok=True)
                    except Exception as e:
                        self._bp_log(f"  ⚠️ dossier sortie inaccessible: {e}")
                        final_dir = os.path.dirname(current_file)
                else:
                    final_dir = os.path.dirname(current_file)

                final_path = os.path.join(final_dir, final_name)

                if current_file != final_path:
                    try:
                        # Never silently delete an existing output file — use a unique name instead
                        if os.path.exists(final_path):
                            root, ext2 = os.path.splitext(final_path)
                            counter = 2
                            while os.path.exists(final_path):
                                final_path = f"{root} ({counter}){ext2}"
                                counter += 1
                            self._bp_log(f"  ℹ️ destination existante → renommé en {os.path.basename(final_path)}")
                        os.rename(current_file, final_path)
                        if final_name != os.path.basename(current_file):
                            self._bp_log(f"  renommé → {final_name}")
                        if use_output_dir:
                            self._bp_log(f"  → {final_dir}")
                    except Exception as e:
                        self._bp_log(f"  ⚠️ déplacement/renommage échoué: {e}")
                elif use_output_dir and final_dir != os.path.dirname(current_file):
                    self._bp_log(f"  ℹ️ fichier déjà à destination")

                self._bp_log(f"  ✓ terminé")

            except Exception as e:
                logger.error(f"Batch Pro error on {base_name}: {e}")
                self._bp_log(f"  ⚠️ erreur: {e}")

            self.cleanup_temp(self.temp_files)
            done += 1
            total = len(files)
            elapsed = time.time() - start_time
            eta = (elapsed / done) * (total - done) if done > 0 else 0
            percent = int(done / total * 100) if total else 100

            def _fmt(sec):
                return f"{int(sec // 60)}m {int(sec % 60)}s"

            status = (f"{done}/{total} ({percent}%)  •  "
                      f"Écoulé: {_fmt(elapsed)}  •  ETA: {_fmt(eta)}")
            self.after(0, lambda v=done, st=status: (
                self.bp_progress.configure(value=v),
                self.bp_status_lbl.config(text=st),
            ))

        total_time = time.time() - start_time
        self._bp_log(f"━━ Pipeline terminé en {int(total_time // 60)}m {int(total_time % 60)}s ━━")
        self.after(0, lambda: (
            self.bp_run_btn.config(state='normal'),
            self.bp_status_lbl.config(
                text=f"✓ Terminé — {done}/{len(files)} fichiers en "
                     f"{int(total_time // 60)}m {int(total_time % 60)}s", fg='#008000'),
        ))
        threading.Thread(target=notify_toast,
                         args=(f"Batch Pro — {T('notif_batch_done')}",
                               T('notif_batch_body').format(s=done, e=0)),
                         daemon=True).start()


# ============================================================================
# MAIN APPLICATION CLASS
# ============================================================================

class PyMkvPropEdit:
    def __init__(self, root):
        self.root = root
        self.root.title(f"PyMkvPropEdit v{VERSION} - Batch GUI pour mkvpropedit")
        self.style = ttk.Style(self.root)
        self.style.theme_use('clam')

        # Icon — use wm_iconbitmap for proper multi-res taskbar icon
        try:
            icon_path = resolve_asset("vivi.ico")
            if os.path.exists(icon_path):
                self.root.wm_iconbitmap(icon_path)
        except Exception as e:
            logger.warning(f"Icon load failed: {e}")

        # Settings
        self.settings_file = SETTINGS_FILE
        self.presets_file = PRESETS_FILE
        self.settings = self.load_settings()
        self.presets = self.load_presets()

        # Window size — restore saved, always centered on screen
        self.window_width = self.settings.get('window_width', 1450)
        self.window_height = self.settings.get('window_height', 920)
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - self.window_width) // 2
        y = max(0, (sh - self.window_height) // 2)
        self.root.geometry(f"{self.window_width}x{self.window_height}+{x}+{y}")

        self.theme = self.settings.get('theme', 'light')
        self.save_tracks_var = tk.BooleanVar(value=self.settings.get('save_tracks', True))
        self.apply_chapter_names_var = tk.BooleanVar(value=self.settings.get('apply_chapter_names', False))
        self.detailed_output_var = tk.BooleanVar(value=self.settings.get('detailed_output', False))
        self.delete_tags_var = tk.BooleanVar(value=self.settings.get('delete_tags', False))
        self.custom_numbering_var = tk.BooleanVar(value=self.settings.get('custom_numbering', False))
        self.chapters_remove_var = tk.BooleanVar(value=self.settings.get('chapters_remove', False))
        self.notifications_var = tk.BooleanVar(value=self.settings.get('notifications', True))

        # Sync global notifications flag from settings
        global _notifications_enabled
        _notifications_enabled = self.notifications_var.get()

        # Pre-load summary images in background (avoid freeze on first use)
        self._summary_img_cache: dict = {}
        self._preload_summary_images()

        self.apply_theme(self.theme)
        self.languages = LANGUAGES

        # Main notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True)

        self.create_tabs()

        # Drag & drop
        if TkinterDnD is not None:
            try:

                self.file_list.drop_target_register(DND_FILES)

                self.file_list.dnd_bind('<<Drop>>', self.drop_files)

            except Exception:

                logger.warning("tkdnd not available for self.file_list")
        else:
            logger.warning("tkinterdnd2 not available, drag & drop disabled.")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.cancel_processing = False

        # [NEW] Keyboard shortcuts
        self.root.bind('<Control-o>', lambda e: self.add_files())
        self.root.bind('<Control-O>', lambda e: self.add_files())
        self.root.bind('<Control-Shift-O>', lambda e: self.add_folder())
        self.root.bind('<Delete>', lambda e: self.remove_selected())
        self.root.bind('<Control-s>', lambda e: self.save_settings())
        self.root.bind('<Control-S>', lambda e: self.save_settings())

        # [NEW] Status bar
        self.status_bar = tk.Label(self.root, text=f"PyMkvPropEdit v{VERSION} — Prêt", bd=1, relief=tk.SUNKEN, anchor=tk.W, font=("Arial", 9))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self._update_status_bar()

        # First-launch wizard (deferred so UI is fully rendered first)
        self.root.after(200, self._check_first_launch)

    def _check_first_launch(self):
        """Show MKVToolNix wizard on first launch (mkvtools_source not yet in settings)."""
        if 'mkvtools_source' not in self.settings:
            self._show_mkvtools_wizard()

    def _show_mkvtools_wizard(self):
        """First-launch dialog: choose language + system vs bundled MKVToolNix."""
        bundled_dir = os.path.join(_ASSET_DIR, 'mkvtools')
        bundled_available = (
            os.path.isdir(bundled_dir) and
            os.path.exists(os.path.join(bundled_dir, 'mkvpropedit.exe'))
        )

        # Scan ffmpeg before showing dialog (fast enough)
        ffmpeg_installs = _scan_ffmpeg_installs()

        dlg = tk.Toplevel(self.root)
        dlg.title(T('wizard_title'))
        dlg.geometry("580x600")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.transient(self.root)
        dlg.update_idletasks()
        x = (dlg.winfo_screenwidth() - 580) // 2
        y = (dlg.winfo_screenheight() - 600) // 2
        dlg.geometry(f"580x600+{x}+{y}")

        # Set icon
        try:
            icon_path = resolve_asset("vivi.ico")
            if os.path.exists(icon_path):
                dlg.wm_iconbitmap(icon_path)
        except Exception:
            pass

        tk.Label(dlg, text="⚙️  " + T('wizard_title'),
                 font=('Arial', 13, 'bold')).pack(pady=12)

        # ── Language section ──────────────────────────────────────────
        tk.Label(dlg, text=T('wizard_lang_section'),
                 font=('Arial', 10, 'bold')).pack(pady=(4, 0))
        lang_frame = tk.Frame(dlg, bd=1, relief='groove')
        lang_frame.pack(pady=4, padx=24, fill='x')

        wizard_lang_var = tk.StringVar(value=LANG)
        ttk.Radiobutton(lang_frame, text="Français 🇫🇷",
                         variable=wizard_lang_var, value='fr').pack(
            side=tk.LEFT, padx=30, pady=10)
        ttk.Radiobutton(lang_frame, text="English 🇬🇧",
                         variable=wizard_lang_var, value='en').pack(
            side=tk.LEFT, padx=30, pady=10)

        # ── MKVToolNix section ────────────────────────────────────────
        tk.Label(dlg, text=T('wizard_mkv_section'),
                 font=('Arial', 10, 'bold')).pack(pady=(10, 0))
        tk.Label(dlg, text=T('wizard_msg'), font=('Arial', 10)).pack(pady=2)

        mkv_frame = tk.Frame(dlg, bd=1, relief='groove')
        mkv_frame.pack(pady=4, padx=24, fill='x')

        choice_var = tk.StringVar(value='system')

        tk.Radiobutton(
            mkv_frame, text=T('wizard_system'),
            variable=choice_var, value='system',
            justify='left', font=('Arial', 10)
        ).pack(anchor='w', padx=16, pady=8)

        rb_bnd = tk.Radiobutton(
            mkv_frame, text=T('wizard_bundled'),
            variable=choice_var, value='bundled',
            justify='left', font=('Arial', 10),
            state='normal' if bundled_available else 'disabled'
        )
        rb_bnd.pack(anchor='w', padx=16, pady=6)
        if not bundled_available:
            tk.Label(mkv_frame, text=T('wizard_bundled_unavail'),
                     fg='gray', font=('Arial', 8, 'italic')).pack(anchor='w', padx=40, pady=(0, 6))

        # ── FFmpeg section ────────────────────────────────────────────────
        tk.Label(dlg, text=T('wizard_ffmpeg_section'),
                 font=('Arial', 10, 'bold')).pack(pady=(10, 0))

        ffmpeg_frame = tk.Frame(dlg, bd=1, relief='groove')
        ffmpeg_frame.pack(pady=4, padx=24, fill='x')

        ffmpeg_sel_var = tk.StringVar()

        if ffmpeg_installs:
            tk.Label(ffmpeg_frame, text=T('wizard_ffmpeg_found'),
                     font=('Arial', 9)).pack(anchor='w', padx=8, pady=(6, 2))

            lb_frame = tk.Frame(ffmpeg_frame)
            lb_frame.pack(fill='x', padx=8, pady=(0, 6))
            lb_scroll_y = tk.Scrollbar(lb_frame, orient='vertical')
            lb_scroll_x = tk.Scrollbar(lb_frame, orient='horizontal')
            ffmpeg_lb = tk.Listbox(lb_frame, height=min(len(ffmpeg_installs), 4),
                                    yscrollcommand=lb_scroll_y.set,
                                    xscrollcommand=lb_scroll_x.set,
                                    font=('Consolas', 8),
                                    selectmode='single', activestyle='dotbox')
            lb_scroll_y.config(command=ffmpeg_lb.yview)
            lb_scroll_x.config(command=ffmpeg_lb.xview)
            lb_scroll_y.pack(side='right', fill='y')
            lb_scroll_x.pack(side='bottom', fill='x')
            ffmpeg_lb.pack(side='left', fill='both', expand=True)

            for inst in ffmpeg_installs:
                ffmpeg_lb.insert(tk.END, inst['label'])
            ffmpeg_lb.selection_set(0)
            ffmpeg_sel_var.set(ffmpeg_installs[0]['path'])

            def on_lb_select(evt):
                sel = ffmpeg_lb.curselection()
                if sel:
                    ffmpeg_sel_var.set(ffmpeg_installs[sel[0]]['path'])

            ffmpeg_lb.bind('<<ListboxSelect>>', on_lb_select)
        else:
            tk.Label(ffmpeg_frame, text=T('wizard_ffmpeg_none'),
                     fg='gray', font=('Arial', 9, 'italic')).pack(padx=8, pady=6)
            ffmpeg_lb = None

        def browse_wizard_ffmpeg():
            p = filedialog.askopenfilename(
                title="ffmpeg.exe",
                filetypes=[("ffmpeg", "ffmpeg.exe"), ("All", "*.*")]
            )
            if p:
                ffmpeg_sel_var.set(p)
                if ffmpeg_lb is not None:
                    ffmpeg_lb.selection_clear(0, tk.END)

        tk.Button(ffmpeg_frame, text=T('wizard_ffmpeg_browse'),
                  command=browse_wizard_ffmpeg,
                  bg='#555577', fg='white', font=('Arial', 9)).pack(padx=8, pady=(0, 8))

        def on_confirm():
            source = choice_var.get()
            chosen_lang = wizard_lang_var.get()
            self.settings['mkvtools_source'] = source
            self.settings['language'] = chosen_lang

            if source == 'bundled' and bundled_available:
                bp = os.path.join(bundled_dir, 'mkvpropedit.exe')
                bm = os.path.join(bundled_dir, 'mkvmerge.exe')
                self.mkvpropedit_path_entry.delete(0, tk.END)
                self.mkvpropedit_path_entry.insert(0, bp)
                self.mkvmerge_path_entry.delete(0, tk.END)
                self.mkvmerge_path_entry.insert(0, bm)
            else:
                sp = find_system_mkv_tool('mkvpropedit')
                sm = find_system_mkv_tool('mkvmerge')
                self.mkvpropedit_path_entry.delete(0, tk.END)
                self.mkvpropedit_path_entry.insert(0, sp)
                self.mkvmerge_path_entry.delete(0, tk.END)
                self.mkvmerge_path_entry.insert(0, sm)

            # Apply FFmpeg selection
            sel_ff = ffmpeg_sel_var.get()
            if sel_ff and os.path.isfile(sel_ff):
                self.ffmpeg_path_entry.delete(0, tk.END)
                self.ffmpeg_path_entry.insert(0, sel_ff)
                # Derive ffprobe from same dir
                ff_dir = os.path.dirname(sel_ff)
                ffprobe_candidate = os.path.join(ff_dir, 'ffprobe.exe')
                if os.path.isfile(ffprobe_candidate):
                    self.ffprobe_path_entry.delete(0, tk.END)
                    self.ffprobe_path_entry.insert(0, ffprobe_candidate)

            self.save_settings()
            dlg.destroy()

            # Restart if language changed
            if chosen_lang != LANG:
                messagebox.showinfo(
                    "Restart / Redémarrage",
                    T('wizard_restart_needed')
                )
                self.root.destroy()

        tk.Button(dlg, text=T('wizard_confirm'), command=on_confirm,
                  bg='#008000', fg='white', font=('Arial', 10, 'bold'),
                  width=14, pady=4).pack(pady=12)

        self.root.wait_window(dlg)

    def _switch_to_bundled_mkv(self):
        """Options button: switch to bundled MKVToolNix."""
        bundled_dir = os.path.join(_ASSET_DIR, 'mkvtools')
        if not (os.path.isdir(bundled_dir) and
                os.path.exists(os.path.join(bundled_dir, 'mkvpropedit.exe'))):
            messagebox.showwarning("MKVToolNix", T('msg_no_bundled'))
            return
        bp = os.path.join(bundled_dir, 'mkvpropedit.exe')
        bm = os.path.join(bundled_dir, 'mkvmerge.exe')
        self.mkvpropedit_path_entry.delete(0, tk.END)
        self.mkvpropedit_path_entry.insert(0, bp)
        self.mkvmerge_path_entry.delete(0, tk.END)
        self.mkvmerge_path_entry.insert(0, bm)
        self.settings['mkvtools_source'] = 'bundled'
        self.save_settings()
        messagebox.showinfo("MKVToolNix", T('msg_switched_bundled'))

    def _switch_to_system_mkv(self):
        """Options button: switch to system MKVToolNix."""
        sp = find_system_mkv_tool('mkvpropedit')
        sm = find_system_mkv_tool('mkvmerge')
        self.mkvpropedit_path_entry.delete(0, tk.END)
        self.mkvpropedit_path_entry.insert(0, sp)
        self.mkvmerge_path_entry.delete(0, tk.END)
        self.mkvmerge_path_entry.insert(0, sm)
        self.settings['mkvtools_source'] = 'system'
        self.save_settings()

    def _preload_summary_images(self):
        """Preload success/warning/failure background images in a background thread."""
        win_w, win_h = 450, 350

        def _load():
            cache = {}
            for img_name in ('success.jpg', 'warning.jpg', 'failure.jpg'):
                try:
                    p = resolve_asset(img_name)
                    if os.path.exists(p):
                        img = Image.open(p).resize(
                            (win_w, win_h), Image.Resampling.LANCZOS
                        ).convert("RGBA")
                        alpha = img.split()[3].point(lambda v: v * 60 // 100)
                        img.putalpha(alpha)
                        cache[img_name] = img
                except Exception as e:
                    logger.debug(f"Preload {img_name} failed: {e}")
            self.root.after(0, lambda: self._summary_img_cache.update(cache))

        threading.Thread(target=_load, daemon=True).start()

    def _on_notifications_toggle(self):
        """Checkbox callback: sync global flag and save settings."""
        global _notifications_enabled
        _notifications_enabled = self.notifications_var.get()
        self.settings['notifications'] = _notifications_enabled
        self.save_settings()

    def _update_status_bar(self):
        """Update the status bar with file count."""
        count = self.file_list.size()
        text = f"PyMkvPropEdit v{VERSION} — {count} fichier(s) chargé(s)"
        self.status_bar.config(text=text)

    def drop_files(self, event):
        files = self.root.tk.splitlist(event.data)
        for file in files:
            if file.lower().endswith('.mkv'):
                self.file_list.insert(tk.END, file)
        self._update_status_bar()

    # ---- Settings / Presets ----

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Settings load failed: {e}")
        return {}

    def load_presets(self):
        if os.path.exists(self.presets_file):
            try:
                with open(self.presets_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Presets load failed: {e}")
        return {}

    def save_settings(self):
        settings = {
            'mkvpropedit_path': self.mkvpropedit_path_entry.get(),
            'mkvmerge_path': self.mkvmerge_path_entry.get(),
            'general_title': sanitize_input(self.general_title_entry.get()),
            'general_start_num': self.general_start_num_entry.get(),
            'general_padding': self.general_padding_entry.get(),
            'general_extra': sanitize_input(self.general_extra_text.get("1.0", tk.END).strip()),
            'chapters_file': self.chapters_file_entry.get(),
            'chapters_suffix': self.chapters_suffix_entry.get(),
            'chapters_remove': self.chapters_remove_var.get(),
            'apply_chapter_names': self.apply_chapter_names_var.get(),
            'cover_path': self.cover_path_entry.get(),
            'cover_name': sanitize_input(self.cover_name_entry.get()),
            'cover_format': self.cover_format_var.get(),
            'window_width': self.root.winfo_width(),
            'window_height': self.root.winfo_height(),
            'theme': self.theme,
            'save_tracks': self.save_tracks_var.get(),
            'delete_tags': self.delete_tags_var.get(),
            'custom_numbering': self.custom_numbering_var.get(),
            'detailed_output': self.detailed_output_var.get(),
            'audio_sync_duration': self.audio_sync_app.duration_var.get(),
            'audio_sync_start': self.audio_sync_app.start_offset_var.get() if hasattr(self.audio_sync_app, 'start_offset_var') else "300",
            'ffmpeg_path': self.ffmpeg_path_entry.get(),
            'ffprobe_path': self.ffprobe_path_entry.get(),
            'language': self.language_var.get() if hasattr(self, 'language_var') else LANG,
            'mkvtools_source': self.settings.get('mkvtools_source', 'system'),
            'notifications': self.notifications_var.get() if hasattr(self, 'notifications_var') else True,
            # Frame extraction tab settings
            'extract_format': self.extract_frames_app.format_var.get() if hasattr(self, 'extract_frames_app') else 'jpg',
            'extract_mode': self.extract_frames_app.mode_var.get() if hasattr(self, 'extract_frames_app') else 'interval',
            'extract_interval': self.extract_frames_app.interval_entry.get() if hasattr(self, 'extract_frames_app') else '1',
            'extract_jpg_quality': self.extract_frames_app.jpg_quality_var.get() if hasattr(self, 'extract_frames_app') else 2,
            'extract_png_compression': self.extract_frames_app.png_compression_var.get() if hasattr(self, 'extract_frames_app') else 5,
            'extract_auto_folder': self.extract_frames_app.auto_folder_var.get() if hasattr(self, 'extract_frames_app') else True,
            'extract_out_dir': self.extract_frames_app.out_dir_entry.get() if hasattr(self, 'extract_frames_app') else '',
            'extract_range_from': self.extract_frames_app.range_from_var.get() if hasattr(self, 'extract_frames_app') else '0',
            'extract_range_to': self.extract_frames_app.range_to_var.get() if hasattr(self, 'extract_frames_app') else '100',
            # API keys + Batch Pro settings
            'tvdb_api_key': self.tvdb_key_entry.get() if hasattr(self, 'tvdb_key_entry') else self.settings.get('tvdb_api_key', ''),
            'tmdb_api_key': self.tmdb_key_entry.get() if hasattr(self, 'tmdb_key_entry') else self.settings.get('tmdb_api_key', ''),
            'bp_search_lang': self.batch_pro_app.search_lang_var.get() if hasattr(self, 'batch_pro_app') else 'fr',
            'bp_api_provider': self.batch_pro_app.bp_api_var.get() if hasattr(self, 'batch_pro_app') else 'Auto',
            'bp_ref_lang': self.batch_pro_app.bp_ref_lang_var.get() if hasattr(self, 'batch_pro_app') else 'jpn',
            'bp_duration': self.batch_pro_app.bp_duration_var.get() if hasattr(self, 'batch_pro_app') else "120",
            'bp_start': self.batch_pro_app.bp_start_var.get() if hasattr(self, 'batch_pro_app') else "300",
            'bp_preserve_src': self.batch_pro_app.bp_preserve_src_var.get() if hasattr(self, 'batch_pro_app') else False,
            'bp_sync': self.batch_pro_app.bp_sync_var.get() if hasattr(self, 'batch_pro_app') else True,
            'bp_sync_subs': self.batch_pro_app.bp_sync_subs_var.get() if hasattr(self, 'batch_pro_app') else True,
            'bp_props': self.batch_pro_app.bp_props_var.get() if hasattr(self, 'batch_pro_app') else True,
            'bp_reorder': self.batch_pro_app.bp_reorder_var.get() if hasattr(self, 'batch_pro_app') else False,
            'bp_rename': self.batch_pro_app.bp_rename_var.get() if hasattr(self, 'batch_pro_app') else True,
            'bp_embed_meta': self.batch_pro_app.bp_embed_meta_var.get() if hasattr(self, 'batch_pro_app') else False,
            'bp_clean_tags': self.batch_pro_app.bp_clean_tags_var.get() if hasattr(self, 'batch_pro_app') else True,
            'bp_output_dir': self.batch_pro_app.bp_output_dir_var.get() if hasattr(self, 'batch_pro_app') else False,
            'bp_output_path': self.batch_pro_app.bp_output_path_var.get() if hasattr(self, 'batch_pro_app') else '',
            'bp_pane_sizes': self.batch_pro_app._get_pane_sizes() if hasattr(self, 'batch_pro_app') else None,
            'bp_picker_geometry': self.batch_pro_app.settings.get('bp_picker_geometry', '1200x740') if hasattr(self, 'batch_pro_app') else '1200x740',
            'bp_picker_prefs': self.batch_pro_app.settings.get('bp_picker_prefs', {}) if hasattr(self, 'batch_pro_app') else {},
        }
        if self.save_tracks_var.get():
            settings['audio_tracks'] = self._save_tracks(self.audio_frames)
            settings['subtitle_tracks'] = self._save_tracks(self.subtitle_frames)
            settings['video_tracks'] = self._save_tracks(self.video_frames)
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
            # Keep in-memory dict in sync so sub-tabs (AudioSync, etc.) see updated paths
            self.settings.update(settings)
            logger.info("Settings saved.")
        except Exception as e:
            logger.error(f"Settings save failed: {e}")
            messagebox.showerror("Erreur", f"Échec de la sauvegarde des paramètres : {e}")

    def _save_tracks(self, frames):
        tracks = []
        for frame in frames:
            tracks.append({
                'edit': frame['edit_var'].get(),
                'name': sanitize_input(frame['name_entry'].get()),
                'lang': frame['lang_combo'].get(),
                'default': frame['default_var'].get(),
                'forced': frame['forced_var'].get(),
                'extra': sanitize_input(frame['extra_text'].get("1.0", tk.END).strip()),
            })
        return tracks

    # [NEW] Export / Import settings
    def export_settings(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                             filetypes=[("JSON files", "*.json")],
                                             title="Exporter les paramètres")
        if path:
            self.save_settings()
            try:
                shutil.copy2(self.settings_file, path)
                messagebox.showinfo("Succès", f"Paramètres exportés vers :\n{path}")
            except Exception as e:
                messagebox.showerror("Erreur", f"Export échoué : {e}")

    def import_settings(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")],
                                           title="Importer des paramètres")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    imported = json.load(f)
                with open(self.settings_file, 'w', encoding='utf-8') as f:
                    json.dump(imported, f, ensure_ascii=False, indent=4)
                messagebox.showinfo("Succès", "Paramètres importés. Redémarrez l'application pour appliquer.")
            except Exception as e:
                messagebox.showerror("Erreur", f"Import échoué : {e}")

    def save_preset(self):
        preset_name = sanitize_input(self.preset_name_entry.get().strip())
        if not preset_name:
            messagebox.showwarning("Avertissement", "Veuillez entrer un nom pour le preset.")
            return
        preset_data = {
            'video_tracks': self._save_tracks(self.video_frames),
            'audio_tracks': self._save_tracks(self.audio_frames),
            'subtitle_tracks': self._save_tracks(self.subtitle_frames)
        }
        self.presets[preset_name] = preset_data
        try:
            with open(self.presets_file, 'w', encoding='utf-8') as f:
                json.dump(self.presets, f, ensure_ascii=False, indent=4)
            self.preset_combo['values'] = list(self.presets.keys())
            self.preset_combo.set(preset_name)
            messagebox.showinfo("Succès", f"Preset '{preset_name}' sauvegardé !")
        except Exception as e:
            messagebox.showerror("Erreur", f"Échec sauvegarde preset : {e}")

    def load_preset(self):
        preset_name = self.preset_combo.get()
        if not preset_name or preset_name not in self.presets:
            messagebox.showwarning("Avertissement", "Sélectionnez un preset valide.")
            return
        preset_data = self.presets[preset_name]
        for frame in self.video_frames:
            frame['frame'].destroy()
        for frame in self.audio_frames:
            frame['frame'].destroy()
        for frame in self.subtitle_frames:
            frame['frame'].destroy()
        self.video_frames.clear()
        self.audio_frames.clear()
        self.subtitle_frames.clear()
        self.load_tracks(self.video_scroll_frame, self.video_frames, 'Video', preset_data.get('video_tracks', []))
        self.load_tracks(self.audio_scroll_frame, self.audio_frames, 'Audio', preset_data.get('audio_tracks', []))
        self.load_tracks(self.subtitle_scroll_frame, self.subtitle_frames, 'Subtitle', preset_data.get('subtitle_tracks', []))
        messagebox.showinfo("Succès", f"Preset '{preset_name}' chargé !")

    def delete_preset(self):
        preset_name = self.preset_combo.get()
        if not preset_name or preset_name not in self.presets:
            messagebox.showwarning("Avertissement", "Sélectionnez un preset valide.")
            return
        del self.presets[preset_name]
        try:
            with open(self.presets_file, 'w', encoding='utf-8') as f:
                json.dump(self.presets, f, ensure_ascii=False, indent=4)
            self.preset_combo['values'] = list(self.presets.keys())
            self.preset_combo.set('')
            messagebox.showinfo("Succès", f"Preset '{preset_name}' supprimé !")
        except Exception as e:
            messagebox.showerror("Erreur", f"Échec suppression preset : {e}")

    def validate_numeric_input(self, entry, field_name):
        try:
            value = int(entry.get())
            if value < 0:
                raise ValueError
            return value
        except ValueError:
            messagebox.showwarning("Entrée invalide", f"Entier non négatif requis pour {field_name}.")
            entry.delete(0, tk.END)
            entry.insert(0, "0")
            return 0

    # ---- Theme ----

    def apply_theme(self, theme):
        self.theme = theme
        if theme == 'light':
            bg_color = '#f0f0f0'; fg_color = '#333333'; btn_bg = '#00DC59'; btn_fg = '#333333'
            entry_bg = '#ffffff'; tab_bg = '#dddddd'; tab_fg = '#333333'
            progress_fg = '#00DC59'; progress_bg = '#ffffff'
            canvas_colors = {'video': '#fffde7', 'audio': '#e3f2fd', 'subtitle': '#e8f5e9'}
            tree_bg = '#ffffff'; tree_fg = '#000000'; tree_even = '#f0f0f0'; tree_odd = '#ffffff'
            check_selectcolor = '#ffffff'; check_hover_bg = '#e0e0e0'
        else:
            bg_color = '#333333'; fg_color = '#ffffff'; btn_bg = '#00DC59'; btn_fg = '#333333'
            entry_bg = '#444444'; tab_bg = '#363636'; tab_fg = '#ffffff'
            progress_fg = '#00DC59'; progress_bg = '#444444'
            canvas_colors = {'video': '#4A4A2E', 'audio': '#2E4A4A', 'subtitle': '#2E4A2E'}
            tree_bg = '#444444'; tree_fg = '#ffffff'; tree_even = '#555555'; tree_odd = '#444444'
            check_selectcolor = '#444444'; check_hover_bg = '#555555'

        self.root.configure(bg=bg_color)
        self.style.configure('TFrame', background=bg_color)
        self.style.configure('TLabel', background=bg_color, foreground=fg_color)
        self.style.configure('TButton', background=btn_bg, foreground=btn_fg)
        self.style.configure('TEntry', fieldbackground=entry_bg, foreground=fg_color)
        self.style.configure('Custom.TEntry', fieldbackground=entry_bg, foreground=fg_color)
        self.style.configure('Custom.TCombobox', fieldbackground=entry_bg, foreground=fg_color)
        self.style.configure('TCheckbutton', background=bg_color, foreground=fg_color,
                             selectcolor=check_selectcolor)
        self.style.map('TCheckbutton', background=[('active', check_hover_bg)], foreground=[('active', fg_color)])
        self.style.configure('Custom.Treeview', background=tree_bg, foreground=tree_fg,
                             fieldbackground=tree_bg, rowheight=25)
        self.style.configure('Custom.Treeview.Heading', background=tab_bg, foreground=tab_fg)
        self.style.configure('Video.TFrame', background=canvas_colors['video'])
        self.style.configure('Audio.TFrame', background=canvas_colors['audio'])
        self.style.configure('Subtitle.TFrame', background=canvas_colors['subtitle'])
        self.style.configure('TNotebook', background=bg_color)
        self.style.configure('TNotebook.Tab', background=tab_bg, foreground=tab_fg)
        self.style.map('TNotebook.Tab', background=[('selected', entry_bg)], foreground=[('selected', fg_color)])
        self.style.configure('TProgressbar', troughcolor=progress_bg, background=progress_fg)

        if hasattr(self, 'input_tab'):
            self._update_widget_colors(self.root, bg_color, fg_color, entry_bg, canvas_colors)
            for canvas_name in ['video_canvas', 'audio_canvas', 'subtitle_canvas']:
                if hasattr(self, canvas_name):
                    canvas = getattr(self, canvas_name)
                    key = canvas_name.split('_')[0]
                    canvas.config(bg=canvas_colors.get(key, bg_color), highlightthickness=0, borderwidth=0)
            if hasattr(self, 'chapters_tree'):
                self.chapters_tree.tag_configure('evenrow', background=tree_even)
                self.chapters_tree.tag_configure('oddrow', background=tree_odd)
                self._update_chapter_tags()

    def _update_widget_colors(self, widget, bg_color, fg_color, entry_bg, canvas_colors):
        try:
            if isinstance(widget, tk.Canvas):
                return
            if isinstance(widget, tk.Label):
                widget.config(bg=bg_color, fg=fg_color)
            elif isinstance(widget, (tk.Entry, ttk.Entry)):
                widget.config(bg=entry_bg, fg=fg_color)
            elif isinstance(widget, scrolledtext.ScrolledText):
                widget.config(bg=entry_bg, fg=fg_color)
            elif isinstance(widget, tk.Listbox):
                widget.config(bg=entry_bg, fg=fg_color)
            elif isinstance(widget, tk.Frame):
                widget.config(bg=bg_color)
            elif isinstance(widget, tk.Text):
                widget.config(bg=entry_bg, fg=fg_color)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._update_widget_colors(child, bg_color, fg_color, entry_bg, canvas_colors)

    def change_theme(self):
        self.theme = self.theme_var.get()
        self.apply_theme(self.theme)

    # ---- Tab Creation ----

    def create_tabs(self):
        # INPUT TAB
        self.input_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.input_tab, text=T('tab_input'))
        listbox_frame = tk.Frame(self.input_tab)
        listbox_frame.pack(fill='both', expand=True, pady=5, padx=5)
        self.file_list = tk.Listbox(listbox_frame, selectmode=tk.MULTIPLE, height=10)
        self.input_scrollbar = ttk.Scrollbar(listbox_frame, orient="vertical", command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=self.input_scrollbar.set)
        self.file_list.pack(side="left", fill='both', expand=True)
        self.input_scrollbar.pack(side="right", fill="y")

        btn_frame = tk.Frame(self.input_tab)
        btn_frame.pack(side="bottom", anchor='center', pady=6)
        tk.Button(btn_frame, text=T('btn_add_files'), command=self.add_files, bg='#ADD8E6', fg='#000000').pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text=T('btn_add_folder'), command=self.add_folder, bg='#800080', fg='white').pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text=T('btn_remove'), command=self.remove_selected, bg='#FF4500', fg='white').pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text=T('btn_clear'), command=self.clear_files, bg='#FF0000', fg='white').pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text=T('btn_move_up'), command=self.move_file_up, bg='#0066ff', fg='white').pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text=T('btn_move_down'), command=self.move_file_down, bg='#0066ff', fg='white').pack(side=tk.LEFT, padx=5)

        # OUTPUT TAB
        self.output_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.output_tab, text=T('tab_output'))
        output_controls_frame = tk.Frame(self.output_tab)
        output_controls_frame.pack(fill='x', pady=5)
        ttk.Checkbutton(output_controls_frame, text=T('chk_detailed'), variable=self.detailed_output_var).pack(side=tk.LEFT, padx=5)
        tk.Button(output_controls_frame, text=T('btn_save_log'), command=self.save_log, bg='#008000', fg='white').pack(side=tk.RIGHT, padx=5)
        self.output_text = scrolledtext.ScrolledText(self.output_tab, height=20)
        self.output_text.pack(fill='both', expand=True, pady=5)

        # VIDEO / AUDIO / SUBTITLE TABS
        for tab_name, style_name, canvas_bg, attr_prefix in [
            ("Video", "Video.TFrame", '#fffde7' if self.theme == 'light' else '#4A4A2E', 'video'),
            ("Audio", "Audio.TFrame", '#e3f2fd' if self.theme == 'light' else '#2E4A4A', 'audio'),
            ("Subtitle", "Subtitle.TFrame", '#e8f5e9' if self.theme == 'light' else '#2E4A2E', 'subtitle'),
        ]:
            tab = ttk.Frame(self.notebook, style=style_name)
            tab.pack_propagate(False)
            self.notebook.add(tab, text=tab_name)
            setattr(self, f'{attr_prefix}_tab', tab)

            canvas = tk.Canvas(tab, highlightthickness=0, borderwidth=0, bg=canvas_bg)
            scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
            scroll_frame = ttk.Frame(canvas)
            scroll_frame.bind("<Configure>", lambda e, c=canvas: c.configure(scrollregion=c.bbox("all")))
            canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            setattr(self, f'{attr_prefix}_canvas', canvas)
            setattr(self, f'{attr_prefix}_scroll_frame', scroll_frame)
            frames_list = []
            setattr(self, f'{attr_prefix}_frames', frames_list)

            add_btn = tk.Button(tab, text="+ Add Track",
                                command=lambda p=scroll_frame, fl=frames_list, tt=tab_name: self.add_track(p, fl, tt, self.settings.get(f'{tt.lower()}_tracks', [])),
                                bg='#0066ff', fg='white')
            add_btn.pack(pady=5, padx=(0, 20), anchor='e')
            self.load_tracks(scroll_frame, frames_list, tab_name, self.settings.get(f'{attr_prefix}_tracks', []))

        # CHAPTERS TAB
        self.chapters_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.chapters_tab, text=T('tab_chapters'))
        tk.Label(self.chapters_tab, text=T('lbl_chapters_file')).pack(pady=10)
        self.chapters_file_entry = tk.Entry(self.chapters_tab)
        self.chapters_file_entry.pack(fill='x', padx=5, pady=5)
        btn_frame_chapters_top = tk.Frame(self.chapters_tab)
        btn_frame_chapters_top.pack(pady=5)
        tk.Button(btn_frame_chapters_top, text=T('btn_browse'), command=self.browse_chapters, bg='#008000', fg='white').pack(side='left', padx=5)
        tk.Button(btn_frame_chapters_top, text=T('btn_load_edit'), command=self.load_edit_chapters, bg='#008000', fg='white').pack(side='left', padx=5)

        tree_frame = tk.Frame(self.chapters_tab)
        tree_frame.pack(fill='both', expand=True, pady=5)
        self.chapters_tree = ttk.Treeview(tree_frame, columns=("Num", "Start Time", "End Time", "Name"), show="headings", height=10, style='Custom.Treeview')
        for col, text, width in [("Num", "Numéro", 50), ("Start Time", "Début", 150), ("End Time", "Fin", 150), ("Name", "Nom", 300)]:
            self.chapters_tree.heading(col, text=text)
            self.chapters_tree.column(col, width=width, anchor='center' if col != "Name" else 'w')
        self.chapters_tree.pack(side="left", fill='both', expand=True)
        chapters_sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.chapters_tree.yview)
        chapters_sb.pack(side="right", fill="y")
        self.chapters_tree.configure(yscrollcommand=chapters_sb.set)
        self.chapters_tree.tag_configure('evenrow', background='#f0f0f0' if self.theme == 'light' else '#555555')
        self.chapters_tree.tag_configure('oddrow', background='#ffffff' if self.theme == 'light' else '#444444')
        self.chapters_tree.bind("<Double-1>", self.start_editing)

        btn_frame_chapters = tk.Frame(self.chapters_tab)
        btn_frame_chapters.pack(pady=5)
        tk.Button(btn_frame_chapters, text=T('btn_add_chapter'), command=self.add_chapter, bg='#0066ff', fg='white').pack(side='left', padx=5)
        tk.Button(btn_frame_chapters, text=T('btn_del_chapter'), command=self.remove_chapter, bg='#FF0000', fg='white').pack(side='left', padx=5)
        tk.Label(self.chapters_tab, text=T('lbl_suffix')).pack(pady=10)
        self.chapters_suffix_entry = tk.Entry(self.chapters_tab, width=20)
        self.chapters_suffix_entry.pack(pady=5)
        self.chapters_suffix_entry.insert(0, self.settings.get('chapters_suffix', '.xml'))

        chapters_opts = tk.Frame(self.chapters_tab)
        chapters_opts.pack(pady=10)
        ttk.Checkbutton(chapters_opts, text=T('chk_remove_chapters'), variable=self.chapters_remove_var).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(chapters_opts, text=T('chk_apply_chapter_names'), variable=self.apply_chapter_names_var).pack(side=tk.LEFT, padx=5)

        # COVER IMAGE TAB
        self.attachments_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.attachments_tab, text=T('tab_cover'))
        tk.Label(self.attachments_tab, text=T('lbl_cover_intro'), font=("Arial", 10, "bold")).pack(pady=10)
        tk.Label(self.attachments_tab, text=T('lbl_select_image')).pack(pady=5)
        self.cover_path_entry = tk.Entry(self.attachments_tab, width=50)
        self.cover_path_entry.pack(pady=5)
        self.cover_path_entry.insert(0, self.settings.get('cover_path', ''))
        tk.Button(self.attachments_tab, text=T('btn_browse_image'), command=self.browse_cover_image, bg='#008000', fg='white').pack(pady=5)
        self.cover_preview = tk.Label(self.attachments_tab, text=T('lbl_no_preview'))
        self.cover_preview.pack(pady=5)
        tk.Label(self.attachments_tab, text=T('lbl_attachment_name')).pack(pady=(10, 0))
        self.cover_name_entry = tk.Entry(self.attachments_tab)
        self.cover_name_entry.pack(pady=5)
        self.cover_name_entry.insert(0, self.settings.get('cover_name', 'cover.jpg'))
        tk.Label(self.attachments_tab, text=T('lbl_cover_format')).pack(pady=(10, 0))
        self.cover_format_var = tk.StringVar(value=self.settings.get('cover_format', 'jpg'))
        format_frame = tk.Frame(self.attachments_tab)
        format_frame.pack(pady=5)
        tk.Radiobutton(format_frame, text="JPG", variable=self.cover_format_var, value="jpg").pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(format_frame, text="PNG", variable=self.cover_format_var, value="png").pack(side=tk.LEFT, padx=10)

        # GENERAL TAB
        self.general_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.general_tab, text=T('tab_general'))
        tk.Label(self.general_tab, text=T('lbl_title_field')).pack(pady=10)
        self.general_title_entry = tk.Entry(self.general_tab, width=50)
        self.general_title_entry.pack(pady=10)
        self.general_title_entry.insert(0, self.settings.get('general_title', ''))

        numbering_frame = tk.Frame(self.general_tab)
        numbering_frame.pack(pady=10)
        ttk.Checkbutton(numbering_frame, text=T('chk_custom_numbering'), variable=self.custom_numbering_var).pack(side=tk.LEFT, padx=5)
        tk.Label(numbering_frame, text=T('lbl_start_num')).pack(side=tk.LEFT, padx=5)
        self.general_start_num_entry = tk.Entry(numbering_frame, width=5)
        self.general_start_num_entry.pack(side=tk.LEFT, padx=5)
        self.general_start_num_entry.insert(0, self.settings.get('general_start_num', '1'))
        tk.Label(numbering_frame, text=T('lbl_padding')).pack(side=tk.LEFT, padx=5)
        self.general_padding_entry = tk.Entry(numbering_frame, width=5)
        self.general_padding_entry.pack(side=tk.LEFT, padx=5)
        self.general_padding_entry.insert(0, self.settings.get('general_padding', '0'))

        ttk.Checkbutton(self.general_tab, text=T('chk_delete_tags'), variable=self.delete_tags_var).pack(pady=10)
        tk.Label(self.general_tab, text=T('lbl_extra_params')).pack(pady=10)
        self.general_extra_text = scrolledtext.ScrolledText(self.general_tab, height=10, width=60)
        self.general_extra_text.pack(pady=10)
        self.general_extra_text.insert(tk.END, self.settings.get('general_extra', ''))

        # PRESETS TAB
        self.presets_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.presets_tab, text=T('tab_presets'))
        tk.Label(self.presets_tab, text=T('lbl_preset_name')).pack(pady=10)
        self.preset_name_entry = tk.Entry(self.presets_tab)
        self.preset_name_entry.pack(pady=5)
        tk.Label(self.presets_tab, text=T('lbl_select_preset')).pack(pady=10)
        self.preset_combo = ttk.Combobox(self.presets_tab, values=list(self.presets.keys()), state='readonly')
        self.preset_combo.pack(pady=5)
        btn_frame_presets = tk.Frame(self.presets_tab)
        btn_frame_presets.pack(pady=10)
        tk.Button(btn_frame_presets, text=T('btn_save_preset'), command=self.save_preset, bg='#0066ff', fg='white').pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame_presets, text=T('btn_load_preset'), command=self.load_preset, bg='#008000', fg='white').pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame_presets, text=T('btn_del_preset'), command=self.delete_preset, bg='#FF0000', fg='white').pack(side=tk.LEFT, padx=5)

        # OPTIONS TAB
        self.options_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.options_tab, text=T('tab_options'))
        tk.Label(self.options_tab, text=T('lbl_mkvpropedit_path')).pack(pady=10)
        self.mkvpropedit_path_entry = tk.Entry(self.options_tab, width=50)
        self.mkvpropedit_path_entry.pack(pady=10)
        self.mkvpropedit_path_entry.insert(0, self.settings.get('mkvpropedit_path', find_system_mkv_tool('mkvpropedit')))
        tk.Button(self.options_tab, text=T('btn_browse'), command=self.browse_mkvpropedit, bg='#008000', fg='white').pack(pady=5)
        tk.Label(self.options_tab, text=T('lbl_mkvmerge_path')).pack(pady=10)
        self.mkvmerge_path_entry = tk.Entry(self.options_tab, width=50)
        self.mkvmerge_path_entry.pack(pady=10)
        self.mkvmerge_path_entry.insert(0, self.settings.get('mkvmerge_path', find_system_mkv_tool('mkvmerge')))
        tk.Button(self.options_tab, text=T('btn_browse'), command=self.browse_mkvmerge, bg='#008000', fg='white').pack(pady=5)

        # Quick-switch bundled/system MKVToolNix
        mkv_switch_frame = tk.Frame(self.options_tab)
        mkv_switch_frame.pack(pady=(0, 6))
        tk.Button(mkv_switch_frame, text=T('btn_use_bundled'),
                  command=self._switch_to_bundled_mkv,
                  bg='#555577', fg='white', font=('Arial', 9)).pack(side=tk.LEFT, padx=4)
        tk.Button(mkv_switch_frame, text=T('btn_use_system'),
                  command=self._switch_to_system_mkv,
                  bg='#555577', fg='white', font=('Arial', 9)).pack(side=tk.LEFT, padx=4)

        tk.Label(self.options_tab, text=T('lbl_ffmpeg_path')).pack(pady=10)
        self.ffmpeg_path_entry = tk.Entry(self.options_tab, width=50)
        self.ffmpeg_path_entry.pack(pady=5)
        self.ffmpeg_path_entry.insert(0, self.settings.get('ffmpeg_path', find_ffmpeg()))
        tk.Button(self.options_tab, text=T('btn_browse'), command=self.browse_ffmpeg, bg='#008000', fg='white').pack(pady=5)

        tk.Label(self.options_tab, text=T('lbl_ffprobe_path')).pack(pady=10)
        self.ffprobe_path_entry = tk.Entry(self.options_tab, width=50)
        self.ffprobe_path_entry.pack(pady=5)
        self.ffprobe_path_entry.insert(0, self.settings.get('ffprobe_path', find_ffprobe()))
        tk.Button(self.options_tab, text=T('btn_browse'), command=self.browse_ffprobe, bg='#008000', fg='white').pack(pady=5)

        # API keys for Batch Pro auto-rename
        tk.Label(self.options_tab, text=T('lbl_tvdb_key')).pack(pady=(10, 0))
        self.tvdb_key_entry = tk.Entry(self.options_tab, width=50, show='*')
        self.tvdb_key_entry.pack(pady=4)
        self.tvdb_key_entry.insert(0, self.settings.get('tvdb_api_key', ''))

        tk.Label(self.options_tab, text=T('lbl_tmdb_key')).pack(pady=(8, 0))
        self.tmdb_key_entry = tk.Entry(self.options_tab, width=50, show='*')
        self.tmdb_key_entry.pack(pady=4)
        self.tmdb_key_entry.insert(0, self.settings.get('tmdb_api_key', ''))

        tk.Label(self.options_tab, text=T('lbl_theme')).pack(pady=10)
        theme_frame = tk.Frame(self.options_tab)
        theme_frame.pack(pady=10)
        self.theme_var = tk.StringVar(value=self.theme)
        ttk.Radiobutton(theme_frame, text=T('lbl_theme_light'), variable=self.theme_var, value="light", command=self.change_theme).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(theme_frame, text=T('lbl_theme_dark'), variable=self.theme_var, value="dark", command=self.change_theme).pack(side='left', padx=10)

        tk.Label(self.options_tab, text=T('lbl_language_app')).pack(pady=(15, 0))
        lang_frame = tk.Frame(self.options_tab)
        lang_frame.pack(pady=5)
        self.language_var = tk.StringVar(value=LANG)
        ttk.Radiobutton(lang_frame, text="Français 🇫🇷", variable=self.language_var, value="fr").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(lang_frame, text="English 🇬🇧", variable=self.language_var, value="en").pack(side=tk.LEFT, padx=10)
        tk.Label(self.options_tab, text=T('lbl_restart_required'), fg='gray', font=("Arial", 9, "italic")).pack()

        ttk.Checkbutton(self.options_tab, text=T('lbl_save_tracks'), variable=self.save_tracks_var).pack(pady=10)
        ttk.Checkbutton(self.options_tab, text=T('lbl_notifications'),
                         variable=self.notifications_var,
                         command=self._on_notifications_toggle).pack(pady=4)

        # [NEW] Export/Import buttons
        io_frame = tk.Frame(self.options_tab)
        io_frame.pack(pady=10)
        tk.Button(io_frame, text=T('btn_export_settings'), command=self.export_settings, bg='#0066ff', fg='white').pack(side=tk.LEFT, padx=5)
        tk.Button(io_frame, text=T('btn_import_settings'), command=self.import_settings, bg='#0066ff', fg='white').pack(side=tk.LEFT, padx=5)

        # AUDIO SYNC TAB
        self.sync_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.sync_tab, text=T('tab_sync'))
        self.audio_sync_app = AudioSyncTab(self.sync_tab, self.settings, self)

        # AUDIO SYNC BATCH TAB
        self.batch_sync_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.batch_sync_tab, text=T('tab_sync_batch'))
        self.audio_sync_batch_app = AudioSyncBatchTab(self.batch_sync_tab, self.settings, self)

        # BATCH PRO TAB
        self.batch_pro_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.batch_pro_tab, text=T('tab_batchpro'))
        self.batch_pro_app = BatchProTab(self.batch_pro_tab, self.settings, self)

        # FRAME CHECK BATCH TAB
        self.frame_check_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.frame_check_tab, text=T('tab_frame_check'))
        self.frame_check_app = FrameCheckBatchTab(self.frame_check_tab, self.settings)

        # FRAME EXTRACTION TAB
        self.extract_frames_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.extract_frames_tab, text=T('tab_extract'))
        self.extract_frames_app = FrameExtractTab(self.extract_frames_tab, self.settings)

        # [NEW] MEDIA INFO TAB
        self.mediainfo_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.mediainfo_tab, text=T('tab_mediainfo'))
        self.mediainfo_app = MediaInfoTab(self.mediainfo_tab, self.settings)

        # ABOUT TAB
        self.about_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.about_tab, text=T('tab_about'))
        self.about_canvas = tk.Canvas(self.about_tab, highlightthickness=0, borderwidth=0)
        self.about_canvas.pack(fill='both', expand=True)
        try:
            bg_path = resolve_asset("backroom.jpg")
            if os.path.exists(bg_path):
                image = Image.open(bg_path)
                image = image.resize((self.window_width, self.window_height - 40), Image.Resampling.LANCZOS)
                image = image.convert("RGBA")
                alpha = image.split()[3]
                alpha = alpha.point(lambda p: p * 0.7)
                image.putalpha(alpha)
                self.about_image = ImageTk.PhotoImage(image)
                self.about_canvas.create_image(self.window_width // 2, 0, image=self.about_image, anchor='n')
        except Exception as e:
            logger.debug(f"About background load failed: {e}")

        about_text = (
            f"PyMkvPropEdit v{VERSION}\n\n"
            "Une interface graphique pour mkvpropedit permettant de modifier\n"
            "les propriétés des fichiers MKV en lot.\n"
            "Inspirée par JMkvpropedit avec des paramètres persistants\n"
            "et des fonctionnalités améliorées.\n\n"
            "Raccourcis clavier :\n"
            "  Ctrl+O : Ajouter des fichiers\n"
            "  Ctrl+Shift+O : Ajouter un dossier\n"
            "  Suppr : Supprimer sélection\n"
            "  Ctrl+S : Sauvegarder paramètres"
        )
        self.about_canvas.create_text(20, 20, text=f"PyMkvPropEdit v{VERSION}", justify=tk.LEFT, font=("Arial Black", 24, "bold"), anchor='nw')
        self.about_canvas.create_text(20, 70, text=about_text[len(f"PyMkvPropEdit v{VERSION}\n"):], justify=tk.LEFT, font=("Arial", 11), anchor='nw')

        # PROGRESS & PROCESS BUTTONS
        self.progress_frame = tk.Frame(self.root)
        self.progress_frame.pack(anchor='center', pady=10)
        self.progress = ttk.Progressbar(self.progress_frame, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(side=tk.LEFT, padx=10)
        tk.Button(self.progress_frame, text=T('btn_process'), command=self.process_files, bg='#00DC59', fg='#333333').pack(side=tk.LEFT, padx=5)
        tk.Button(self.progress_frame, text=T('btn_cancel'), command=self.cancel_process, bg='#FF0000', fg='white').pack(side=tk.LEFT, padx=5)

        # Hide bottom process bar when Batch Pro tab is active (it has its own pipeline runner)
        self.notebook.bind('<<NotebookTabChanged>>', self._on_tab_changed)

    def _on_tab_changed(self, event=None):
        """Hide the propedit process bar/buttons when Batch Pro tab is active."""
        try:
            current = self.notebook.select()
            is_batch_pro = (current == str(self.batch_pro_tab))
            if is_batch_pro:
                self.progress_frame.pack_forget()
            else:
                if not self.progress_frame.winfo_ismapped():
                    self.progress_frame.pack(anchor='center', pady=10)
        except Exception as e:
            logger.debug(f"Tab change handler: {e}")

    # ---- File management ----

    def add_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Fichiers MKV", "*.mkv")])
        for f in files:
            self.file_list.insert(tk.END, f)
        self._update_status_bar()

    def add_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            for f in glob.glob(os.path.join(folder, "**/*.mkv"), recursive=True):
                self.file_list.insert(tk.END, f)
            self._update_status_bar()

    def remove_selected(self):
        for i in self.file_list.curselection()[::-1]:
            self.file_list.delete(i)
        self._update_status_bar()

    def clear_files(self):
        self.file_list.delete(0, tk.END)
        self._update_status_bar()

    def move_file_up(self):
        for i in self.file_list.curselection():
            if i == 0:
                continue
            text = self.file_list.get(i)
            self.file_list.delete(i)
            self.file_list.insert(i - 1, text)
            self.file_list.select_set(i - 1)

    def move_file_down(self):
        for i in reversed(self.file_list.curselection()):
            if i == self.file_list.size() - 1:
                continue
            text = self.file_list.get(i)
            self.file_list.delete(i)
            self.file_list.insert(i + 1, text)
            self.file_list.select_set(i + 1)

    # ---- Track management ----

    def add_track(self, parent, frames_list, track_type, saved_tracks=None):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=5)
        edit_var = tk.BooleanVar()
        edit_check = ttk.Checkbutton(frame, text=f"Edit Track {track_type} {len(frames_list) + 1}", variable=edit_var)
        edit_check.pack(side=tk.LEFT, padx=5)
        ToolTip(edit_check, "Active la modification des propriétés de cette piste.")
        tk.Label(frame, text="Name:").pack(side=tk.LEFT, padx=5)
        name_entry = ttk.Entry(frame, style='Custom.TEntry')
        name_entry.pack(side=tk.LEFT, padx=5)
        tk.Label(frame, text="Lang:").pack(side=tk.LEFT, padx=5)
        lang_combo = ttk.Combobox(frame, values=self.languages, width=20, style='Custom.TCombobox')
        lang_combo.pack(side=tk.LEFT, padx=5)
        default_var = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Default", variable=default_var).pack(side=tk.LEFT, padx=5)
        forced_var = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Forced", variable=forced_var).pack(side=tk.LEFT, padx=5)
        tk.Label(frame, text="Extra:").pack(side=tk.LEFT, padx=5)
        extra_text = tk.Text(frame, height=1, width=20, bg='#444444' if self.theme == 'dark' else '#ffffff')
        extra_text.pack(side=tk.LEFT, padx=5)
        up_btn = tk.Button(frame, text="↑", bg='#FFC107', fg='black')
        up_btn.pack(side=tk.LEFT, padx=5)
        down_btn = tk.Button(frame, text="↓", bg='#FFC107', fg='black')
        down_btn.pack(side=tk.LEFT, padx=5)
        remove_btn = tk.Button(frame, text="Remove", command=lambda: self._remove_track(frame, frames_list), bg='#FF0000', fg='white')
        remove_btn.pack(side=tk.RIGHT, padx=5)

        frame_dict = {
            'frame': frame, 'edit_var': edit_var, 'name_entry': name_entry,
            'lang_combo': lang_combo, 'default_var': default_var, 'forced_var': forced_var,
            'extra_text': extra_text, 'up_btn': up_btn, 'down_btn': down_btn
        }
        frames_list.append(frame_dict)

        if saved_tracks and len(frames_list) <= len(saved_tracks):
            saved = saved_tracks[len(frames_list) - 1]
            edit_var.set(saved.get('edit', False))
            name_entry.insert(0, saved.get('name', ''))
            lang_combo.set(saved.get('lang', 'eng (English)'))
            default_var.set(saved.get('default', False))
            forced_var.set(saved.get('forced', False))
            extra_text.insert(tk.END, saved.get('extra', ''))

        self._repack_tracks(frames_list)

    def load_tracks(self, parent, frames_list, track_type, saved_tracks):
        for i in range(len(saved_tracks)):
            self.add_track(parent, frames_list, track_type, saved_tracks)
        if not saved_tracks:
            self.add_track(parent, frames_list, track_type)

    def _remove_track(self, frame, frames_list):
        for f in frames_list:
            if f['frame'] == frame:
                frames_list.remove(f)
                break
        frame.destroy()
        self._repack_tracks(frames_list)

    def _move_track_up(self, frames_list, index):
        if index > 0:
            frames_list[index], frames_list[index - 1] = frames_list[index - 1], frames_list[index]
            self._repack_tracks(frames_list)

    def _move_track_down(self, frames_list, index):
        if index < len(frames_list) - 1:
            frames_list[index], frames_list[index + 1] = frames_list[index + 1], frames_list[index]
            self._repack_tracks(frames_list)

    def _repack_tracks(self, frames_list):
        for f in frames_list:
            f['frame'].pack_forget()
        if not frames_list:
            return
        # Infer track type from parent widget name
        track_type = 'Track'
        parent_str = str(frames_list[0]['frame'].winfo_parent()) if frames_list else ''
        for tt in ['Video', 'Audio', 'Subtitle']:
            if tt.lower() in parent_str.lower():
                track_type = tt
                break
        for i, f in enumerate(frames_list):
            f['frame'].pack(fill='x', pady=5)
            for child in f['frame'].winfo_children():
                if isinstance(child, ttk.Checkbutton):
                    try:
                        text = child.cget('text')
                        if text.startswith("Edit Track"):
                            child.config(text=f"Edit Track {track_type} {i + 1}")
                    except tk.TclError:
                        pass
            f['up_btn'].config(command=lambda idx=i: self._move_track_up(frames_list, idx))
            f['down_btn'].config(command=lambda idx=i: self._move_track_down(frames_list, idx))

    # ---- Chapters ----

    def browse_chapters(self):
        path = filedialog.askopenfilename(filetypes=[("Fichiers XML", "*.xml")])
        if path:
            self.chapters_file_entry.delete(0, tk.END)
            self.chapters_file_entry.insert(0, path)
            self.load_edit_chapters()

    def load_edit_chapters(self):
        chapters_file = self.chapters_file_entry.get()
        if not chapters_file or not os.path.exists(chapters_file):
            messagebox.showwarning("Avertissement", "Aucun fichier de chapitres valide sélectionné !")
            return
        try:
            tree = ET.parse(chapters_file)
            root = tree.getroot()
            if root.tag != 'Chapters':
                raise ValueError("Le fichier XML n'est pas un fichier de chapitres valide.")
            self.chapters_tree.delete(*self.chapters_tree.get_children())
            for i, chapter in enumerate(root.findall(".//ChapterAtom")):
                chapter_start = chapter.find(".//ChapterTimeStart")
                chapter_end = chapter.find(".//ChapterTimeEnd")
                chapter_name = chapter.find(".//ChapterDisplay/ChapterString")
                start_text = chapter_start.text[:12] if chapter_start is not None and chapter_start.text else ""
                end_text = chapter_end.text[:12] if chapter_end is not None and chapter_end.text else ""
                name_text = chapter_name.text if chapter_name is not None else ""
                self.chapters_tree.insert("", "end", values=(str(i + 1), start_text, end_text, name_text))
            self._update_chapter_tags()
        except Exception as e:
            messagebox.showerror("Erreur", f"Échec du chargement des chapitres : {e}")

    def start_editing(self, event):
        item = self.chapters_tree.identify_row(event.y)
        column = self.chapters_tree.identify_column(event.x)
        if not item or not column:
            return
        col_index = int(column[1]) - 1
        values = self.chapters_tree.item(item, "values")
        original_value = values[col_index]
        bbox = self.chapters_tree.bbox(item, column)
        if not bbox:
            return
        entry = ttk.Entry(self.chapters_tree)
        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        entry.insert(0, original_value)
        entry.focus_set()
        entry.select_range(0, tk.END)

        def finish_editing(event=None):
            self.chapters_tree.set(item, column, entry.get())
            entry.destroy()

        entry.bind("<Return>", finish_editing)
        entry.bind("<FocusOut>", finish_editing)
        entry.bind("<Escape>", lambda e: entry.destroy())

    def add_chapter(self):
        self.chapters_tree.insert("", "end", values=("", "", "", ""))
        self.chapters_tree.selection_set(self.chapters_tree.get_children()[-1])
        self._update_chapter_tags()

    def remove_chapter(self):
        for item in self.chapters_tree.selection():
            self.chapters_tree.delete(item)
        self._update_chapter_tags()

    def _update_chapter_tags(self):
        for i, item in enumerate(self.chapters_tree.get_children()):
            tag = 'evenrow' if i % 2 == 0 else 'oddrow'
            self.chapters_tree.item(item, tags=(tag,))

    # ---- Cover Image ----

    def browse_cover_image(self):
        filetypes = [("Image files", "*.jpg *.jpeg *.png *.bmp *.gif"), ("All files", "*.*")]
        path = filedialog.askopenfilename(title="Sélectionner une image de couverture", filetypes=filetypes)
        if path:
            self.cover_path_entry.delete(0, tk.END)
            self.cover_path_entry.insert(0, path)
            ext = os.path.splitext(path)[1].lstrip('.').lower()
            if ext in ['jpg', 'jpeg']:
                self.cover_format_var.set('jpg')
                name = "cover.jpg"
            elif ext == 'png':
                self.cover_format_var.set('png')
                name = "cover.png"
            else:
                name = "cover." + ext
            self.cover_name_entry.delete(0, tk.END)
            self.cover_name_entry.insert(0, name)
            try:
                image = Image.open(path)
                image = image.resize((100, 100), Image.Resampling.LANCZOS)
                self.cover_image = ImageTk.PhotoImage(image)
                self.cover_preview.configure(image=self.cover_image, text="")
            except Exception as e:
                self.cover_preview.configure(image=None, text=f"Erreur : {e}")

    # ---- Browsing helpers ----

    def browse_mkvpropedit(self):
        path = filedialog.askopenfilename(title="Sélectionner l'exécutable mkvpropedit")
        if path:
            self.mkvpropedit_path_entry.delete(0, tk.END)
            self.mkvpropedit_path_entry.insert(0, path)

    def browse_mkvmerge(self):
        path = filedialog.askopenfilename(title="Sélectionner l'exécutable mkvmerge")
        if path:
            self.mkvmerge_path_entry.delete(0, tk.END)
            self.mkvmerge_path_entry.insert(0, path)

    def browse_ffmpeg(self):
        path = filedialog.askopenfilename(title="Sélectionner l'exécutable FFmpeg",
                                           filetypes=[("FFmpeg", "ffmpeg*"), ("All", "*.*")])
        if path:
            self.ffmpeg_path_entry.delete(0, tk.END)
            self.ffmpeg_path_entry.insert(0, path)

    def browse_ffprobe(self):
        path = filedialog.askopenfilename(title="Sélectionner l'exécutable FFprobe",
                                           filetypes=[("FFprobe", "ffprobe*"), ("All", "*.*")])
        if path:
            self.ffprobe_path_entry.delete(0, tk.END)
            self.ffprobe_path_entry.insert(0, path)

    def save_log(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.output_text.get("1.0", tk.END))
            messagebox.showinfo("Succès", "Log sauvegardé !")

    # ---- Processing ----

    def get_track_cmds(self, frames, track_prefix):
        cmds = []
        for i, frame in enumerate(frames, 1):
            if frame['edit_var'].get():
                track_cmd = ["--edit", f"track:{track_prefix}{i}"]
                name = sanitize_input(frame['name_entry'].get())
                # Always set name when track edit is checked (empty string clears old name)
                track_cmd += ["--set", f"name={name}"]
                lang = frame['lang_combo'].get().split()[0]
                if lang:
                    track_cmd += ["--set", f"language={lang}"]
                track_cmd += ["--set", f"flag-default={'1' if frame['default_var'].get() else '0'}"]
                track_cmd += ["--set", f"flag-forced={'1' if frame['forced_var'].get() else '0'}"]
                extra = sanitize_input(frame['extra_text'].get("1.0", tk.END).strip())
                if extra:
                    track_cmd += shlex.split(extra)
                cmds += track_cmd
        return cmds

    def build_mkvpropedit_cmd(self, file):
        cmd = [self.mkvpropedit_path_entry.get(), file]
        if self.delete_tags_var.get():
            cmd += ["--delete-tag", "all"]
        cover_path = self.cover_path_entry.get()
        if cover_path and os.path.exists(cover_path):
            attachment_ids = self._check_attachments(file)
            for aid in attachment_ids:
                cmd += ["--delete-attachment", str(aid)]
            mime_type = "image/jpeg" if self.cover_format_var.get() == "jpg" else "image/png"
            cover_name = sanitize_input(self.cover_name_entry.get()) or "cover.jpg"
            cmd += [
                "--attachment-mime-type", mime_type,
                "--attachment-name", cover_name,
                "--attachment-description", "Couverture",
                "--add-attachment", cover_path
            ]
        title = sanitize_input(self.general_title_entry.get().replace("{file_name}", os.path.basename(file).rsplit('.', 1)[0]))
        if title:
            cmd += ["--edit", "info", "--set", f"title={title}"]
        cmd += self.get_track_cmds(self.audio_frames, 'a')
        cmd += self.get_track_cmds(self.subtitle_frames, 's')
        cmd += self.get_track_cmds(self.video_frames, 'v')
        if self.chapters_remove_var.get():
            cmd += ["--delete-chapters"]
        chapters_file = self.chapters_file_entry.get()
        temp_xml = None
        if self.apply_chapter_names_var.get():
            temp_xml = self._apply_chapter_names(file)
            if temp_xml:
                cmd += ["--chapters", temp_xml]
        elif chapters_file and os.path.exists(chapters_file):
            cmd += ["--chapters", chapters_file]
        extra = sanitize_input(self.general_extra_text.get("1.0", tk.END).strip())
        if extra:
            cmd += shlex.split(extra)
        return cmd if len(cmd) > 2 else None

    def _check_attachments(self, file):
        mkvmerge_path = self.mkvmerge_path_entry.get()
        try:
            result = run_hidden([mkvmerge_path, "-J", file])
            info = json.loads(result.stdout)
            return [att['id'] for att in info.get("attachments", [])
                    if att.get('file_name', '').lower().startswith('cover')]
        except Exception as e:
            logger.warning(f"Attachment check failed: {e}")
            return []

    def _get_file_info(self, file):
        """Get formatted file info string (deduplicated track iteration)."""
        mkvmerge_path = self.mkvmerge_path_entry.get()
        try:
            result = run_hidden([mkvmerge_path, "-J", file])
            info = json.loads(result.stdout)
            output = "Contenu du fichier MKV :\n"

            type_labels = {"video": "Pistes vidéo", "audio": "Pistes audio", "subtitles": "Pistes de sous-titres"}
            for ttype, label in type_labels.items():
                output += f"{label} :\n"
                for track in info.get("tracks", []):
                    if track["type"] == ttype:
                        tid = track.get('id', 'N/A')
                        tid = tid + 1 if isinstance(tid, int) else tid
                        name = track.get('properties', {}).get('track_name', 'Sans nom')
                        lang = track.get('properties', {}).get('language', 'N/A')
                        codec = track.get('codec', 'N/A')
                        output += f" - Piste {tid}: {name} ({lang}, {codec})\n"

            output += "Pièces jointes :\n"
            for att in info.get("attachments", []):
                output += f" - {att.get('file_name', 'N/A')} ({att.get('content_type', 'N/A')})\n"
            return output + "\n"
        except Exception as e:
            return f"Erreur info pour {file} : {e}\n"

    def _validate_track_indices(self, file):
        mkvmerge_path = self.mkvmerge_path_entry.get()
        try:
            result = run_hidden([mkvmerge_path, "-J", file])
            info = json.loads(result.stdout)
            tracks = info.get("tracks", [])
            counts = {tt: sum(1 for t in tracks if t["type"] == tt) for tt in ["video", "audio", "subtitles"]}
            configs = {
                "video": sum(1 for f in self.video_frames if f['edit_var'].get()),
                "audio": sum(1 for f in self.audio_frames if f['edit_var'].get()),
                "subtitles": sum(1 for f in self.subtitle_frames if f['edit_var'].get()),
            }
            if any(configs[tt] > counts[tt] for tt in counts):
                self.output_text.insert(tk.END, f"Avertissement : Mismatch de pistes pour {file}\n")
                return False
            if self.detailed_output_var.get():
                self.output_text.insert(tk.END, self._get_file_info(file))
            return True
        except Exception as e:
            logger.warning(f"Track validation failed: {e}")
            self.output_text.insert(tk.END, f"⚠️ Validation ignorée pour {os.path.basename(file)}: {e}\n")
            return True

    def _apply_chapter_names(self, file):
        mkvextract_path = self.settings.get('mkvextract_path') or find_system_mkv_tool('mkvextract')
        temp_orig_xml = None
        try:
            result_extract = run_hidden([mkvextract_path, "chapters", file])
            if result_extract.returncode != 0:
                return None
            with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as _tmp:
                temp_orig_xml = _tmp.name
            with open(temp_orig_xml, 'w', encoding='utf-8') as f:
                f.write(result_extract.stdout)
            tree_orig = ET.parse(temp_orig_xml)
            root_orig = tree_orig.getroot()
            if root_orig.tag != 'Chapters':
                safe_remove(temp_orig_xml)
                return None
            chapters_orig = root_orig.findall(".//ChapterAtom")
            tree_items = self.chapters_tree.get_children()
            if len(chapters_orig) != len(tree_items):
                safe_remove(temp_orig_xml)
                return None
            for i, chapter in enumerate(chapters_orig):
                values = self.chapters_tree.item(tree_items[i])['values']
                chapter_display = chapter.find(".//ChapterDisplay")
                if chapter_display is None:
                    chapter_display = ET.SubElement(chapter, "ChapterDisplay")
                chapter_name = chapter_display.find("ChapterString")
                if chapter_name is not None:
                    chapter_name.text = values[3]
                else:
                    ET.SubElement(chapter_display, "ChapterString").text = values[3]
                if chapter_display.find("ChapterLanguage") is None:
                    ET.SubElement(chapter_display, "ChapterLanguage").text = "und"
            edited_xml = ET.tostring(root_orig, encoding='utf-8', method='xml', xml_declaration=True).decode('utf-8')
            temp_xml = f"{file}_chapters_temp_{uuid.uuid4().hex}.xml"
            with open(temp_xml, 'w', encoding='utf-8') as f:
                f.write(edited_xml)
            safe_remove(temp_orig_xml)
            return temp_xml
        except Exception as e:
            logger.error(f"Chapter names application failed: {e}")
            safe_remove(temp_orig_xml)
            return None

    def process_file(self, args):
        file, cmd, chapters_file, temp_xml = args
        if self.cancel_processing:
            return (file, "Traitement annulé.\n", False)
        try:
            process = popen_hidden(cmd)
            stdout, stderr = process.communicate()
            output = f"Traitement de {file} :\n{stdout}\n{stderr}\n\n"
            if process.returncode != 0:
                output += f"Erreur mkvpropedit (code {process.returncode}) : {stderr}\n"
            safe_remove(temp_xml)
            return (file, output, process.returncode == 0)
        except Exception as e:
            safe_remove(temp_xml)
            return (file, f"Erreur pour {file} : {e}\n\n", False)

    def process_files(self):
        self.cancel_processing = False
        start_time = time.time()
        start_num = self.validate_numeric_input(self.general_start_num_entry, "Starting Number")
        padding = self.validate_numeric_input(self.general_padding_entry, "Padding")
        mkvpropedit = self.mkvpropedit_path_entry.get()

        # ── Validate tool paths upfront ────────────────────────────────────
        mkv_ok = os.path.isfile(mkvpropedit) or shutil.which(mkvpropedit)
        if not mkv_ok:
            messagebox.showerror(
                "mkvpropedit introuvable" if LANG == 'fr' else "mkvpropedit not found",
                f"mkvpropedit non trouvé :\n{mkvpropedit}\n\n"
                "Vérifiez le chemin dans l'onglet Options."
                if LANG == 'fr' else
                f"mkvpropedit not found:\n{mkvpropedit}\n\n"
                "Check the path in the Options tab."
            )
            return

        files = list(self.file_list.get(0, tk.END))
        if not files:
            messagebox.showwarning("Avertissement", "Aucun fichier ajouté !")
            return

        self.output_text.delete("1.0", tk.END)
        self.progress['maximum'] = len(files)
        self.progress['value'] = 0
        self.status_bar.config(text=f"Traitement de {len(files)} fichier(s) en cours...")

        tasks = []
        skipped_errors = []

        for idx, file in enumerate(files):
            if self.cancel_processing:
                break
            if not self._validate_track_indices(file):
                self.output_text.insert(tk.END, f"Fichier {os.path.basename(file)} sauté (mismatch pistes).\n\n")
                skipped_errors.append(f"{os.path.basename(file)} (mismatch)")
                self.progress['value'] += 1
                self.root.update_idletasks()
                continue

            cmd = [mkvpropedit, file]
            if self.delete_tags_var.get():
                cmd += ["--delete-tag", "all"]
            cover_path = self.cover_path_entry.get()
            if cover_path and os.path.exists(cover_path):
                for aid in self._check_attachments(file):
                    cmd += ["--delete-attachment", str(aid)]
                mime_type = "image/jpeg" if self.cover_format_var.get() == "jpg" else "image/png"
                cover_name = sanitize_input(self.cover_name_entry.get()) or "cover.jpg"
                cmd += ["--attachment-mime-type", mime_type, "--attachment-name", cover_name,
                        "--attachment-description", "Couverture", "--add-attachment", cover_path]

            title = sanitize_input(self.general_title_entry.get().replace("{file_name}", os.path.basename(file).rsplit('.', 1)[0]))
            if title:
                if self.custom_numbering_var.get():
                    num = str(idx + start_num).zfill(padding)
                    title = f"[{num}] {title}"
                cmd += ["--edit", "info", "--set", f"title={title}"]

            cmd += self.get_track_cmds(self.audio_frames, 'a')
            cmd += self.get_track_cmds(self.subtitle_frames, 's')
            cmd += self.get_track_cmds(self.video_frames, 'v')

            if self.chapters_remove_var.get():
                cmd += ["--delete-chapters"]

            chapters_file = self.chapters_file_entry.get()
            temp_xml = None
            if self.apply_chapter_names_var.get():
                temp_xml = self._apply_chapter_names(file)
                if temp_xml:
                    cmd += ["--chapters", temp_xml]
            elif chapters_file and os.path.exists(chapters_file):
                cmd += ["--chapters", chapters_file]

            extra = sanitize_input(self.general_extra_text.get("1.0", tk.END).strip())
            if extra:
                cmd += shlex.split(extra)

            if self.detailed_output_var.get():
                self.output_text.insert(tk.END, f"Commande: {' '.join(cmd)}\n")

            tasks.append((file, cmd, chapters_file, temp_xml))

        # Sequential one-at-a-time pipeline for incremental progress bar
        self._proc_state = {
            'tasks': list(tasks),
            'done': self.progress['value'],   # count of already-skipped files
            'total': len(files),              # total files in list
            'task_count': len(tasks),         # tasks to actually run
            'successes': [],
            'errors': list(skipped_errors),
            'start_time': start_time,
            'file_times': [],                 # elapsed time per file, for ETA
        }
        self.root.after(0, self._run_next_task)

    def _run_next_task(self):
        """Main-thread: launch next task in a background thread."""
        st = self._proc_state
        if self.cancel_processing or not st['tasks']:
            self._finish_batch()
            return

        task = st['tasks'].pop(0)
        current = st['done'] + 1
        total = st['total']

        # Status bar: counter + ETA
        if st['file_times']:
            avg = sum(st['file_times']) / len(st['file_times'])
            remaining = len(st['tasks'])        # files still queued
            eta_s = int(avg * remaining)
            m, s = divmod(eta_s, 60)
            eta_str = f" — ETA {m}m{s:02d}s" if m else f" — ETA {s}s"
        else:
            eta_str = ""
        self.status_bar.config(
            text=f"Traitement {current}/{total}{eta_str}  ·  "
                 f"{total - current} restant(s)" if LANG == 'fr'
            else f"Processing {current}/{total}{eta_str}  ·  "
                 f"{total - current} remaining"
        )

        file_start = time.time()

        def _run():
            result = self.process_file(task)
            elapsed = time.time() - file_start
            self.root.after(0, lambda r=result, e=elapsed: self._on_task_done(r, e))

        threading.Thread(target=_run, daemon=True).start()

    def _on_task_done(self, result, elapsed):
        """Main-thread: called after each file completes."""
        st = self._proc_state
        file, output, success = result

        st['file_times'].append(elapsed)
        st['done'] += 1

        if success:
            st['successes'].append(file)
        else:
            st['errors'].append(os.path.basename(file))

        # Update output + progress bar
        self.output_text.insert(tk.END, output)
        self.output_text.see(tk.END)
        self.progress.configure(value=st['done'])
        self.root.update_idletasks()

        # Schedule next file (small delay so UI renders)
        self.root.after(20, self._run_next_task)

    def _finish_batch(self):
        """Main-thread: all files done."""
        st = self._proc_state
        total_seconds = time.time() - st['start_time']
        self._update_status_bar()
        # Run toast in background so it never blocks the summary window
        title = T('notif_batch_done')
        body = T('notif_batch_body').format(s=len(st['successes']), e=len(st['errors']))
        threading.Thread(target=notify_toast, args=(title, body), daemon=True).start()
        self.show_summary_window(st['successes'], st['errors'], total_seconds)

    def _update_execute_ui(self, output, progress_val):
        self.output_text.insert(tk.END, output)
        self.output_text.see(tk.END)
        self.progress.configure(value=progress_val)

    def cancel_process(self):
        self.cancel_processing = True
        self.output_text.insert(tk.END, "Annulation du traitement en cours...\n")
        self.output_text.see(tk.END)

    def format_time(self, seconds):
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s" if seconds > 0 else "0s"

    def show_summary_window(self, successes, errors, total_seconds):
        summary_window = tk.Toplevel(self.root)
        summary_window.title(T('summary_title'))
        summary_window.transient(self.root)
        summary_window.grab_set()
        win_w, win_h = 450, 350
        pos_x = self.root.winfo_rootx() + (self.root.winfo_width() - win_w) // 2
        pos_y = self.root.winfo_rooty() + (self.root.winfo_height() - win_h) // 2
        summary_window.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")

        try:
            icon_path = resolve_asset("vivi.ico")
            if os.path.exists(icon_path):
                summary_window.wm_iconbitmap(icon_path)
        except Exception:
            pass

        canvas = tk.Canvas(summary_window, highlightthickness=0, borderwidth=0)
        canvas.pack(fill='both', expand=True)

        # Use pre-loaded cached image (no freeze) or fallback to inline load
        img_name = "success.jpg" if not errors else ("warning.jpg" if successes else "failure.jpg")
        caption = T('summary_caption_success') if not errors else (
            T('summary_caption_warning') if successes else T('summary_caption_failure'))

        pil_img = self._summary_img_cache.get(img_name)
        if pil_img is None:
            # Fallback: load inline if cache not ready yet
            try:
                p = resolve_asset(img_name)
                if os.path.exists(p):
                    pil_img = Image.open(p).resize(
                        (win_w, win_h), Image.Resampling.LANCZOS
                    ).convert("RGBA")
                    alpha = pil_img.split()[3].point(lambda v: v * 60 // 100)
                    pil_img.putalpha(alpha)
            except Exception as e:
                logger.debug(f"Summary image load failed: {e}")

        if pil_img is not None:
            self.summary_image = ImageTk.PhotoImage(pil_img)
            canvas.create_image(win_w // 2, win_h // 2, image=self.summary_image, anchor='center')

        y_pos = 20
        canvas.create_text(win_w // 2, y_pos, text=T('summary_title'),
                            font=("Arial", 14, "bold"), anchor='center')
        y_pos += 40
        canvas.create_text(win_w // 2, y_pos,
                            text=f"{T('summary_success')} : {len(successes)}",
                            font=("Arial", 12, "bold"), fill='#00CC00', anchor='center')
        y_pos += 25
        canvas.create_text(win_w // 2, y_pos,
                            text=f"{T('summary_errors')} : {len(errors)}",
                            font=("Arial", 12, "bold"), fill='#FF3333', anchor='center')
        y_pos += 25
        canvas.create_text(win_w // 2, y_pos,
                            text=f"{T('summary_duration')} : {self.format_time(total_seconds)}",
                            font=("Arial", 12, "italic"), anchor='center')
        y_pos += 50

        if errors:
            def show_errors():
                ew = tk.Toplevel(summary_window)
                ew.title(T('summary_errors_title'))
                ew.transient(summary_window)
                et = tk.Text(ew, height=10, width=80)
                for ef in errors:
                    et.insert(tk.END, ef + "\n")
                et.config(state='disabled')
                et.pack(fill='both', expand=True, padx=5, pady=5)
                tk.Button(ew, text="OK", command=ew.destroy).pack(pady=5)

            error_btn = tk.Button(summary_window, text=T('summary_see_errors'),
                                  command=show_errors, bg='#FF4500', fg='white')
            canvas.create_window(win_w // 2, y_pos, window=error_btn, anchor='center')
            y_pos += 40

        ok_btn = tk.Button(summary_window, text="OK", command=summary_window.destroy,
                           bg='#008000', fg='white', width=10)
        canvas.create_window(win_w // 2, y_pos, window=ok_btn, anchor='center')

    def on_close(self):
        self.save_settings()
        self.root.destroy()


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()  # Required for PyInstaller frozen builds
    logger.info(f"PyMkvPropEdit v{VERSION} starting...")
    try:
        if TkinterDnD is not None:
            root = TkinterDnD.Tk()
        else:
            root = tk.Tk()
        app = PyMkvPropEdit(root)
        root.mainloop()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        messagebox.showerror("Erreur fatale", f"Une erreur s'est produite : {e}")
