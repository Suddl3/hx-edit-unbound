"""Every test runs without the user's own settings.json and HX_EDIT_NAM_* variables: those turn on the
firmware's extra blocks and the mode chooser, which would open Windows dialogs in the middle of a test.

Nor with the user's own %LOCALAPPDATA%\\HX Edit NAM (the library, settings, trace.log, DSP costs...): test runs were
writing into the player's real trace.log (seen 2026-11-27). LOCALAPPDATA points at a temporary folder before any of the
app's modules is imported, since they work out their paths when they load (nam_library.FOLDER, nam_catalog.SETTINGS,
the launcher's TRACE), and at a fresh one for each test (for what reads it later: a launcher loaded inside a test,
the WebView profiles)."""
import atexit
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

import pytest

LOCAL = Path(tempfile.mkdtemp(prefix='hx-edit-tests-'))
os.environ['LOCALAPPDATA'] = str(LOCAL)
atexit.register(shutil.rmtree, LOCAL, True)

# The app's code lives in src/ (the repository root holds the README, docs and tests).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


@pytest.fixture(autouse=True)
def no_user_settings(monkeypatch, tmp_path):
    for name in ('HX_EDIT_NAM_LAYERS', 'HX_EDIT_NAM_PEDAL', 'HX_EDIT_NAM_FIRMWARE'):
        monkeypatch.delenv(name, raising=False)
    local = tmp_path / 'LocalAppData'
    local.mkdir()
    monkeypatch.setenv('LOCALAPPDATA', str(local))
    monkeypatch.setattr('nam_modes.CACHE', tmp_path / 'Converted')     # not the user's converted cache
    monkeypatch.setattr('tone3000.LINKS', tmp_path / 'tone-links.json')  # nor their TONE3000 links
    with patch('nam_catalog.load_settings', return_value={}):
        yield
