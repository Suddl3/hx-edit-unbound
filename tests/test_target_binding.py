"""Native typed target binding verified offline; no live application or device."""
from pathlib import Path
import re
import shutil
import struct
import subprocess

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'src'
# A prepared copy of stock HX Edit 3.82 kept outside the repository; tests that need it skip without it.
FIXTURE = SOURCE.parents[2] / 'research/hx-edit-nam-review/floor-port/integrated-candidate-53/app/HX Edit.exe'


def test_bound_target_native_api_contract():
    node = shutil.which('node')
    if not node:
        pytest.skip('node not installed')
    result = subprocess.run([node, str(SOURCE.parent / 'tests' / 'target_binding_probe.cjs')],
                            capture_output=True, text=True, timeout=30, cwd=SOURCE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'target binding probe passed' in result.stdout


def test_a_snapshot_is_renamed_in_the_edit_buffer_with_one_undo_step():
    node = shutil.which('node')
    if not node:
        pytest.skip('node not installed')
    result = subprocess.run([node, str(SOURCE.parent / 'tests' / 'rename_snapshot_probe.cjs')],
                            capture_output=True, text=True, timeout=30, cwd=SOURCE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'rename snapshot probe passed' in result.stdout


def _reader(path):
    data = path.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    count = struct.unpack_from('<H', data, pe + 6)[0]
    section = pe + 24 + struct.unpack_from('<H', data, pe + 20)[0]
    sections = [struct.unpack_from('<IIII', data, section + i * 40 + 8) for i in range(count)]
    def read(rva, size):
        offset = next(raw + rva - va for _, va, length, raw in sections if va <= rva < va + length)
        return data[offset:offset + size]
    return read


@pytest.mark.skipif(not FIXTURE.is_file(), reason='pinned editor fixture unavailable')
def test_hx_edits_own_snapshot_rename_is_the_edit_buffers_name_write():
    # HX Edit 3.82 on disk (static study 2026-11-24): its snapshot control's edit (0x26f870) writes "@name" of
    # "snapshot%d" through +0x80, which is +0x7c with flags 0; +0x7c keeps an undo step only for a write whose flags
    # have the top bit set. Menu command 32794 (Rename Snapshot) is HX Edit's command 0x12e, 32791 (Rename) 0xcd.
    read = _reader(FIXTURE)
    assert read(0x8be168, 6) == b'@name\0' and read(0x8be170, 11) == b'snapshot%d\0'
    assert read(0x26f91f, 5) == bytes.fromhex('6868e1cb00')          # push "@name"
    assert read(0x26f957, 6) == bytes.fromhex('ff9080000000')        # call [eax+0x80]
    assert struct.unpack('<I', read(0x963dfc + 0x80, 4))[0] == 0x9185a0
    assert read(0x5185a5, 2) == bytes.fromhex('6a00') and read(0x5185b3, 3) == bytes.fromhex('ff507c')   # flags 0, +0x7c
    assert read(0x517935, 4) == bytes.fromhex('85c90f89')            # test flags; jns: no undo record without the top bit
    table, cases = 0x5b6794, 0x5b6830                                # the menu command -> HX Edit command switch
    def command(menu_id):
        target = struct.unpack('<I', read(table + 4 * read(cases + menu_id - 0x8004, 1)[0], 4))[0] - 0x400000
        return struct.unpack('<I', read(target + 1, 4))[0]             # mov eax, imm32
    assert (command(32791), command(32794), command(32779)) == (0xcd, 0x12e, 0x64)


@pytest.mark.skipif(not FIXTURE.is_file(), reason='pinned editor fixture unavailable')
def test_hx_edits_preset_rename_goes_to_the_stored_preset_not_the_edit_buffer():
    # Why the Workbench does not rename a preset yet: HX Edit's Rename (command 0xcd) is the Librarian's: its handler
    # (0x23fe62) opens the list's inline box, whose end ("plst", "cbl!", 0x244b0e) calls 0x3fb7a0, which builds the
    # Librarian operation 3 ("Failed to rename preset.") with the setlist, the index and the name: the Floor's stored copy.
    read = _reader(FIXTURE)
    assert read(0x23fe62, 5) == bytes.fromhex('3dcd000000')          # cmp eax, 0xcd
    assert read(0x244b0e, 5) == bytes.fromhex('e88d6c1b00')          # call 0x3fb7a0
    assert read(0x3fb80b, 7) == bytes.fromhex('c745d803000000')      # operation = 3
    assert read(0x91cf70, 24) == b'Failed to rename preset.'


@pytest.mark.skipif(not FIXTURE.is_file(), reason='pinned editor fixture unavailable')
def test_bound_native_bytes_and_vtable_contract():
    data = FIXTURE.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    count = struct.unpack_from('<H', data, pe + 6)[0]
    section = pe + 24 + struct.unpack_from('<H', data, pe + 20)[0]
    sections = [struct.unpack_from('<IIII', data, section + i * 40 + 8) for i in range(count)]
    def read(rva, size):
        offset = next(raw + rva - va for _, va, length, raw in sections if va <= rva < va + length)
        return data[offset:offset + size]
    guards = re.findall(r"'([0-9a-f]+)': '([0-9a-f]+)'", (SOURCE / 'target_binding.js').read_text())
    assert len(guards) == 7
    for encoded, expected in guards:
        assert read(int(encoded, 16), len(expected) // 2).hex() == expected
    for offset, target in ((0x7c, 0x9178c0), (0x88, 0x904f50), (0xdc, 0x91aaf0)):
        assert struct.unpack('<I', read(0x963dfc + offset, 4))[0] == target
    # Both dispatch instructions and argument cleanup substantiate the captured ABI.
    assert read(0x229c47, 3) == bytes.fromhex('ff507c')
    assert read(0x229d8a, 6) == bytes.fromhex('ff9088000000')
    assert read(0x504f50 + 0x406, 3) == bytes.fromhex('c21000')
    assert read(0x5183d8, 3) == bytes.fromhex('c21400')
    # HXSliderParamView valueType=0 rounds a float to signed integer tag4;
    # valueType=1 stores float32 tag8. Neither is a double-precision payload.
    assert read(0x23cce1, 11) == bytes.fromhex('f30f2cc0c745bc04000000')
    assert read(0x23cc6a, 12) == bytes.fromhex('c745cc08000000f30f1155d4')
