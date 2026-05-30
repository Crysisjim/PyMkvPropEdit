#!/usr/bin/env python3
"""
PyMkvPropEdit v3.6 - Batch GUI pour mkvpropedit
Refactored with improvements and new features.

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
VERSION = "3.6"

SETTINGS_FILE = os.path.join(APP_DIR, "pymkvpropedit_settings.json")
PRESETS_FILE = os.path.join(APP_DIR, "presets.json")
LOG_FILE = os.path.join(APP_DIR, "pymkvpropedit.log")

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
logger = logging.getLogger("PyMkvPropEdit")
logger.info(f"PyMkvPropEdit v{VERSION} starting...")

# ============================================================================
# WIN11TOAST — Notifications Windows 11
# ============================================================================

try:
    from win11toast import toast as _win11toast
    HAS_WIN11TOAST = True
except ImportError:
    HAS_WIN11TOAST = False


def notify_toast(title, body):
    if not HAS_WIN11TOAST:
        return
    try:
        icon_path = resolve_asset("vivi.ico") if os.path.exists(os.path.join(APP_DIR, "vivi.ico")) else None
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
        'wizard_title': 'Premier lancement — Configuration MKVToolNix',
        'wizard_msg': 'Choisissez comment utiliser les outils MKVToolNix :',
        'wizard_system': 'MKVToolNix système\n(utiliser la version installée sur votre PC)',
        'wizard_bundled': 'MKVToolNix intégré\n(inclus dans l\'app, aucune installation requise)',
        'wizard_bundled_unavail': '(non disponible dans cette version)',
        'wizard_confirm': 'Confirmer',
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
        'wizard_title': 'First Launch — MKVToolNix Configuration',
        'wizard_msg': 'Choose how to use MKVToolNix tools:',
        'wizard_system': 'System MKVToolNix\n(use the version installed on your PC)',
        'wizard_bundled': 'Bundled MKVToolNix\n(included in the app, no installation needed)',
        'wizard_bundled_unavail': '(not available in this build)',
        'wizard_confirm': 'Confirm',
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

        mkvmerge = self.settings.get('mkvmerge_path', 'mkvmerge')
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
        mkvmerge = self.settings.get('mkvmerge_path', 'mkvmerge')
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
        mkvmerge = self.settings.get('mkvmerge_path', 'mkvmerge')
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

                self._apply_delays_batch(mkv_path, tracks_data, mkvmerge)
                if apply_props:
                    base, ext = os.path.splitext(mkv_path)
                    output_file = f"{base}_SYNC{ext}"
                    success, msg = self.apply_mkvpropedit_to_file(output_file, self.parent_app)
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
        notify_toast(T('notif_sync_done'), T('notif_sync_body'))

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
        self.format_var = tk.StringVar(value="jpg")
        ttk.Combobox(line1, textvariable=self.format_var, values=["jpg", "png", "bmp"], width=6, state="readonly").pack(side=tk.LEFT, padx=5)

        self.auto_folder_var = tk.BooleanVar(value=True)
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
        self.jpg_quality_var = tk.IntVar(value=2)
        self.jpg_quality_scale = tk.Scale(line_quality, from_=1, to=31, orient=tk.HORIZONTAL,
                                           variable=self.jpg_quality_var, length=120, showvalue=True)
        self.jpg_quality_scale.pack(side=tk.LEFT, padx=5)

        tk.Label(line_quality, text=T('lbl_png_compression')).pack(side=tk.LEFT, padx=(20, 5))
        self.png_compression_var = tk.IntVar(value=5)
        self.png_compression_scale = tk.Scale(line_quality, from_=0, to=9, orient=tk.HORIZONTAL,
                                               variable=self.png_compression_var, length=100, showvalue=True)
        self.png_compression_scale.pack(side=tk.LEFT, padx=5)

        # Ligne 3 : Fréquence / Mode batch
        line2 = tk.Frame(opts_frame)
        line2.pack(fill='x', padx=5, pady=5)
        tk.Label(line2, text=T('lbl_frequency')).pack(side=tk.LEFT)
        self.mode_var = tk.StringVar(value="interval")
        tk.Radiobutton(line2, text=T('rb_interval'), variable=self.mode_var, value="interval", command=self.toggle_inputs).pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(line2, text=T('rb_all_frames'), variable=self.mode_var, value="all", command=self.toggle_inputs).pack(side=tk.LEFT, padx=10)
        self.interval_lbl = tk.Label(line2, text=T('lbl_every'))
        self.interval_lbl.pack(side=tk.LEFT, padx=(5, 0))
        self.interval_entry = tk.Entry(line2, width=5)
        self.interval_entry.insert(0, "1")
        self.interval_entry.pack(side=tk.LEFT, padx=2)
        tk.Label(line2, text=T('lbl_seconds')).pack(side=tk.LEFT)

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

    def toggle_path_entry(self):
        state = 'disabled' if self.auto_folder_var.get() else 'normal'
        self.out_dir_entry.config(state=state)
        self.btn_browse_out.config(state=state)

    def toggle_inputs(self):
        self.interval_entry.config(state='disabled' if self.mode_var.get() == "all" else 'normal')

    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("Video Files", "*.mkv *.mp4 *.avi *.mov *.hevc *.h265 *.264 *.h264 *.ivf *.webm *.ts")])
        if f:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, f)
            if not self.out_dir_var.get():
                self.out_dir_var.set(os.path.dirname(f))

    def drop_file(self, event):
        files = self.winfo_toplevel().tk.splitlist(event.data)
        if files:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, files[0])
            if not self.out_dir_var.get():
                self.out_dir_var.set(os.path.dirname(files[0]))

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

            if self.mode_var.get() == "interval":
                try:
                    sec = float(self.interval_entry.get())
                    if sec <= 0:
                        raise ValueError
                except ValueError:
                    sec = 1.0
                cmd += ["-vf", f"fps=1/{sec}"]

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
                notify_toast(T('notif_extract_done'), T('notif_extract_body'))
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

        mkvmerge = self.settings.get('mkvmerge_path', 'mkvmerge')
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
# MAIN APPLICATION CLASS
# ============================================================================

class PyMkvPropEdit:
    def __init__(self, root):
        self.root = root
        self.root.title(f"PyMkvPropEdit v{VERSION} - Batch GUI pour mkvpropedit")
        self.style = ttk.Style(self.root)
        self.style.theme_use('clam')

        # Icon
        try:
            icon_path = resolve_asset("vivi.ico")
            if os.path.exists(icon_path):
                icon_img = Image.open(icon_path)
                icon_photo = ImageTk.PhotoImage(icon_img)
                self.root.iconphoto(True, icon_photo)
        except Exception as e:
            logger.warning(f"Icon load failed: {e}")

        # Settings
        self.settings_file = SETTINGS_FILE
        self.presets_file = PRESETS_FILE
        self.settings = self.load_settings()
        self.presets = self.load_presets()

        self.window_width = self.settings.get('window_width', 900)
        self.window_height = self.settings.get('window_height', 650)
        self.root.geometry(f"{self.window_width}x{self.window_height}")

        self.theme = self.settings.get('theme', 'light')
        self.save_tracks_var = tk.BooleanVar(value=self.settings.get('save_tracks', True))
        self.apply_chapter_names_var = tk.BooleanVar(value=self.settings.get('apply_chapter_names', False))
        self.detailed_output_var = tk.BooleanVar(value=self.settings.get('detailed_output', False))
        self.delete_tags_var = tk.BooleanVar(value=self.settings.get('delete_tags', False))
        self.custom_numbering_var = tk.BooleanVar(value=self.settings.get('custom_numbering', False))
        self.chapters_remove_var = tk.BooleanVar(value=self.settings.get('chapters_remove', False))

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
        """First-launch dialog: choose system MKVToolNix vs bundled."""
        bundled_dir = os.path.join(_ASSET_DIR, 'mkvtools')
        bundled_available = (
            os.path.isdir(bundled_dir) and
            os.path.exists(os.path.join(bundled_dir, 'mkvpropedit.exe'))
        )

        dlg = tk.Toplevel(self.root)
        dlg.title(T('wizard_title'))
        dlg.geometry("540x330")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.transient(self.root)
        dlg.update_idletasks()
        x = (dlg.winfo_screenwidth() - 540) // 2
        y = (dlg.winfo_screenheight() - 330) // 2
        dlg.geometry(f"540x330+{x}+{y}")

        # Set icon
        try:
            icon_path = resolve_asset("vivi.ico")
            if os.path.exists(icon_path):
                _wiz_img = Image.open(icon_path)
                _wiz_photo = ImageTk.PhotoImage(_wiz_img)
                dlg.iconphoto(True, _wiz_photo)
        except Exception:
            pass

        choice_var = tk.StringVar(value='system')

        tk.Label(dlg, text="⚙️  " + T('wizard_title'),
                 font=('Arial', 12, 'bold')).pack(pady=14)
        tk.Label(dlg, text=T('wizard_msg'), font=('Arial', 10)).pack(pady=2)

        frame = tk.Frame(dlg, bd=1, relief='groove')
        frame.pack(pady=8, padx=24, fill='x')

        tk.Radiobutton(
            frame, text=T('wizard_system'),
            variable=choice_var, value='system',
            justify='left', font=('Arial', 10)
        ).pack(anchor='w', padx=16, pady=8)

        rb_bnd = tk.Radiobutton(
            frame, text=T('wizard_bundled'),
            variable=choice_var, value='bundled',
            justify='left', font=('Arial', 10),
            state='normal' if bundled_available else 'disabled'
        )
        rb_bnd.pack(anchor='w', padx=16, pady=8)
        if not bundled_available:
            tk.Label(frame, text=T('wizard_bundled_unavail'),
                     fg='gray', font=('Arial', 8, 'italic')).pack(anchor='w', padx=40)

        def on_confirm():
            source = choice_var.get()
            self.settings['mkvtools_source'] = source
            if source == 'bundled' and bundled_available:
                bp = os.path.join(bundled_dir, 'mkvpropedit.exe')
                bm = os.path.join(bundled_dir, 'mkvmerge.exe')
                self.mkvpropedit_path_entry.delete(0, tk.END)
                self.mkvpropedit_path_entry.insert(0, bp)
                self.mkvmerge_path_entry.delete(0, tk.END)
                self.mkvmerge_path_entry.insert(0, bm)
            else:
                sp = shutil.which('mkvpropedit') or 'mkvpropedit'
                sm = shutil.which('mkvmerge') or 'mkvmerge'
                self.mkvpropedit_path_entry.delete(0, tk.END)
                self.mkvpropedit_path_entry.insert(0, sp)
                self.mkvmerge_path_entry.delete(0, tk.END)
                self.mkvmerge_path_entry.insert(0, sm)
            self.save_settings()
            dlg.destroy()

        tk.Button(dlg, text=T('wizard_confirm'), command=on_confirm,
                  bg='#008000', fg='white', font=('Arial', 10, 'bold'),
                  width=14, pady=4).pack(pady=14)

        self.root.wait_window(dlg)

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
        }
        if self.save_tracks_var.get():
            settings['audio_tracks'] = self._save_tracks(self.audio_frames)
            settings['subtitle_tracks'] = self._save_tracks(self.subtitle_frames)
            settings['video_tracks'] = self._save_tracks(self.video_frames)
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
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
        self.mkvpropedit_path_entry.insert(0, self.settings.get('mkvpropedit_path', shutil.which('mkvpropedit') or 'mkvpropedit'))
        tk.Button(self.options_tab, text=T('btn_browse'), command=self.browse_mkvpropedit, bg='#008000', fg='white').pack(pady=5)
        tk.Label(self.options_tab, text=T('lbl_mkvmerge_path')).pack(pady=10)
        self.mkvmerge_path_entry = tk.Entry(self.options_tab, width=50)
        self.mkvmerge_path_entry.pack(pady=10)
        self.mkvmerge_path_entry.insert(0, self.settings.get('mkvmerge_path', shutil.which('mkvmerge') or 'mkvmerge'))
        tk.Button(self.options_tab, text=T('btn_browse'), command=self.browse_mkvmerge, bg='#008000', fg='white').pack(pady=5)

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
                if name:
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
        mkvextract_path = shutil.which('mkvextract') or 'mkvextract'
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

        initial_progress = self.progress['value']
        threading.Thread(
            target=self._execute_tasks,
            args=(tasks, skipped_errors, start_time, initial_progress),
            daemon=True
        ).start()

    def _execute_tasks(self, tasks, initial_errors, start_time, initial_progress):
        successes = []
        errors = list(initial_errors)
        progress_val = initial_progress

        for task in tasks:
            if self.cancel_processing:
                break
            result = self.process_file(task)
            file, output, success = result
            progress_val += 1
            pv = progress_val
            self.after(0, lambda o=output, v=pv: self._update_execute_ui(o, v))
            if success:
                successes.append(file)
            else:
                errors.append(os.path.basename(file))

        end_time = time.time()
        total_seconds = end_time - start_time
        self.after(0, self._update_status_bar)
        self.after(0, lambda s=list(successes), e=list(errors), t=total_seconds: self.show_summary_window(s, e, t))
        notify_toast(T('notif_batch_done'), T('notif_batch_body').format(s=len(successes), e=len(errors)))

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
        summary_window.title("Résumé du Traitement")
        summary_window.transient(self.root)
        summary_window.grab_set()
        win_w, win_h = 450, 350
        pos_x = self.root.winfo_rootx() + (self.root.winfo_width() - win_w) // 2
        pos_y = self.root.winfo_rooty() + (self.root.winfo_height() - win_h) // 2
        summary_window.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")

        canvas = tk.Canvas(summary_window, highlightthickness=0, borderwidth=0)
        canvas.pack(fill='both', expand=True)

        # Try to load background
        img_name = "success.jpg" if not errors else ("warning.jpg" if successes else "failure.jpg")
        try:
            img_path = resolve_asset(img_name)
            if os.path.exists(img_path):
                image = Image.open(img_path).resize((win_w, win_h), Image.Resampling.LANCZOS).convert("RGBA")
                alpha = image.split()[3].point(lambda p: p * 0.6)
                image.putalpha(alpha)
                self.summary_image = ImageTk.PhotoImage(image)
                canvas.create_image(win_w // 2, win_h // 2, image=self.summary_image, anchor='center')
        except Exception as e:
            logger.debug(f"Summary image load failed: {e}")

        y_pos = 20
        canvas.create_text(win_w // 2, y_pos, text="Résumé du Traitement", font=("Arial", 14, "bold"), anchor='center')
        y_pos += 40
        canvas.create_text(win_w // 2, y_pos, text=f"Succès : {len(successes)}", font=("Arial", 12, "bold"), fill='#00AA00', anchor='center')
        y_pos += 25
        canvas.create_text(win_w // 2, y_pos, text=f"Erreurs : {len(errors)}", font=("Arial", 12, "bold"), fill='#FF0000', anchor='center')
        y_pos += 25
        canvas.create_text(win_w // 2, y_pos, text=f"Durée : {self.format_time(total_seconds)}", font=("Arial", 12, "italic"), anchor='center')
        y_pos += 50

        if errors:
            def show_errors():
                ew = tk.Toplevel(summary_window)
                ew.title("Fichiers en Erreur")
                ew.transient(summary_window)
                et = tk.Text(ew, height=10, width=80)
                for ef in errors:
                    et.insert(tk.END, ef + "\n")
                et.config(state='disabled')
                et.pack(fill='both', expand=True, padx=5, pady=5)
                tk.Button(ew, text="OK", command=ew.destroy).pack(pady=5)

            error_btn = tk.Button(summary_window, text="Voir les erreurs", command=show_errors, bg='#FF4500', fg='white')
            canvas.create_window(win_w // 2, y_pos, window=error_btn, anchor='center')
            y_pos += 40

        ok_btn = tk.Button(summary_window, text="OK", command=summary_window.destroy, bg='#008000', fg='white', width=10)
        canvas.create_window(win_w // 2, y_pos, window=ok_btn, anchor='center')

    def on_close(self):
        self.save_settings()
        self.root.destroy()


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
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
