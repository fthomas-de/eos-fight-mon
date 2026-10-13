import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import update  # noqa: E402

NEW = b"new binary"
NAME = f"eos-fight-mon-v9.0.0{update.SUFFIX}"


def fake_get(files):
    return lambda url, timeout=10: io.BytesIO(files[url])


class UpdateTest(unittest.TestCase):
    def test_version_order(self):
        self.assertLess(update._key("v0.4.0"), update._key("v0.10.0"))
        self.assertEqual(update._key("v0.5.0"), update._key("0.5.0"))

    def test_latest_only_when_newer(self):
        rel = b'{"tag_name": "%s", "assets": [{"name": "a", "browser_download_url": "u"}]}'
        with mock.patch.object(update, "_get", lambda url: io.BytesIO(rel % b"v9.0.0")):
            self.assertEqual(update.latest(), ("v9.0.0", {"a": "u"}))
        with mock.patch.object(update, "_get", lambda url: io.BytesIO(rel % update.VERSION.encode())):
            self.assertIsNone(update.latest())

    def _install(self, sums):
        d = Path(tempfile.mkdtemp())
        exe = d / "eos-fight-mon.exe"
        exe.write_bytes(b"old binary")
        files = {"bin": NEW, "sums": sums}
        with mock.patch.object(update, "_get", fake_get(files)):
            try:
                update.install({NAME: "bin", "SHA256SUMS.txt": "sums"}, exe)
            except ValueError:
                pass
        return d, exe

    def test_install_swaps_the_exe(self):
        d, exe = self._install(f"{hashlib.sha256(NEW).hexdigest()} *{NAME}\n".encode())
        self.assertEqual(exe.read_bytes(), NEW)
        self.assertFalse((d / "eos-fight-mon.exe.new").exists())

    def test_bad_checksum_keeps_the_old_exe(self):
        d, exe = self._install(f"{'0' * 64} *{NAME}\n".encode())
        self.assertEqual(exe.read_bytes(), b"old binary")
        self.assertEqual([p.name for p in d.iterdir()], ["eos-fight-mon.exe"])


if __name__ == "__main__":
    unittest.main()
