"""Exercise installer failure recovery and authentication gates without hardware."""
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('verimark', Path(__file__).resolve().parents[1] / 'tools/verimark.py')
vm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vm)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.library = self.root / 'opt/lib'
        self.dropin = self.root / 'etc/override.conf'
        self.state = self.root / 'state'
        self.pairfile = self.root / 'private/persistent.bin'
        self.pamdir = self.root / 'pam'
        self.pamdir.mkdir()
        (self.pamdir / 'common-auth').write_text('auth required pam_unix.so\n')
        for name, value in [('LIBDIR', self.library), ('DROPIN', self.dropin),
                            ('STATE', self.state), ('PAIRFILE', self.pairfile), ('PAMDIR', self.pamdir)]:
            p = patch.object(vm, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.calls = []

    def command(self, arguments, **kwargs):
        self.calls.append([str(a) for a in arguments])
        return subprocess.CompletedProcess(arguments, 0, '', '')

    def artifact(self):
        directory = self.root / 'artifact'
        directory.mkdir()
        (directory / vm.LIBNAME).write_bytes(b'synthetic ELF fixture')
        metadata = {'codename': 'noble', 'architecture': platform.machine(),
                    'sha256': hashlib.sha256(b'synthetic ELF fixture').hexdigest()}
        (directory / 'build.json').write_text(json.dumps(metadata))
        return directory

    def test_artifact_rejects_wrong_distribution(self):
        directory = self.artifact()
        metadata = json.loads((directory / 'build.json').read_text())
        metadata['codename'] = 'trixie'
        (directory / 'build.json').write_text(json.dumps(metadata))
        with self.assertRaisesRegex(vm.SetupError, 'incompatible'):
            vm.validate_artifact(directory)

    def test_artifact_rejects_tampering(self):
        directory = self.artifact()
        (directory / vm.LIBNAME).write_bytes(b'changed')
        with self.assertRaisesRegex(vm.SetupError, 'checksum'):
            vm.validate_artifact(directory)

    def test_artifact_checks_soname(self):
        directory = self.artifact()
        with patch.object(vm, 'run', return_value=subprocess.CompletedProcess([], 0, 'wrong soname', '')):
            with self.assertRaisesRegex(vm.SetupError, 'SONAME'):
                vm.validate_artifact(directory)

    def test_readers_filters_exact_usb_id(self):
        for name, vid, pid in [('reader', '047d', '00f2'), ('other', '047d', '00f3')]:
            device = self.root / name
            device.mkdir()
            (device / 'idVendor').write_text(vid)
            (device / 'idProduct').write_text(pid)
        self.assertEqual(vm.readers(self.root), [self.root / 'reader'])

    def test_no_reader_is_a_failure(self):
        with patch.object(vm, 'readers', return_value=[]):
            with self.assertRaisesRegex(vm.SetupError, 'found 0'):
                vm.require_reader()

    def test_absent_usb_sysfs_is_reported_as_no_reader(self):
        self.assertEqual(vm.readers(self.root / 'missing-sysfs'), [])

    def test_multiple_readers_refused(self):
        with patch.object(vm, 'readers', return_value=[1, 2]):
            with self.assertRaisesRegex(vm.SetupError, 'found 2'):
                vm.require_reader()

    def test_private_pairing_rejects_symlinks_and_open_permissions(self):
        file = self.root / 'secret'
        file.write_bytes(b'fixture')
        file.chmod(0o644)
        with self.assertRaises(vm.SetupError):
            vm.private_file(file)
        link = self.root / 'link'
        link.symlink_to(file)
        with self.assertRaises(vm.SetupError):
            vm.private_file(link)

    def test_pam_comments_do_not_count_as_password_fallback(self):
        self.assertFalse(vm.pam_has('# auth required pam_unix.so\n', 'pam_unix.so'))
        self.assertTrue(vm.pam_has('auth [success=1 default=ignore] pam_unix.so nullok\n', 'pam_unix.so'))
        self.assertFalse(vm.pam_has('auth required fake_pam_unix.so\n', 'pam_unix.so'))

    def test_pairing_requires_explicit_acceptance_before_usb_access(self):
        with patch.object(vm, 'require_target'), patch.object(vm, 'require_reader') as reader:
            with self.assertRaisesRegex(vm.SetupError, 'Windows pairing'):
                vm.pair(False)
            reader.assert_not_called()

    def test_login_requires_positive_and_negative_hardware_check(self):
        with patch.object(vm, 'require_target'), patch.object(vm, 'run') as command:
            with self.assertRaisesRegex(vm.SetupError, 'wrong-finger'):
                vm.set_login(True, 'test-user', False)
            command.assert_not_called()

    def test_login_refuses_missing_password_fallback(self):
        (self.pamdir / 'common-auth').write_text('auth required pam_fprintd.so\n')
        with patch.object(vm, 'require_target'), patch.object(vm, 'run') as command:
            with self.assertRaisesRegex(vm.SetupError, 'Password fallback'):
                vm.set_login(True, 'test-user', True)
            command.assert_not_called()

    def test_login_refuses_touch_only_pam_rules(self):
        (self.pamdir / 'sudo').write_text('auth sufficient pam_u2f.so\n')
        with patch.object(vm, 'require_target'), patch.object(vm, 'run', side_effect=self.command):
            with self.assertRaisesRegex(vm.SetupError, 'pam_u2f'):
                vm.set_login(True, 'test-user', True)
        self.assertFalse(any(command[0] == 'pam-auth-update' for command in self.calls))

    def test_login_enable_disable_preserves_password_and_tracks_ownership(self):
        auth = self.pamdir / 'common-auth'
        def command(arguments, **kwargs):
            if arguments[0] == 'fprintd-list':
                return subprocess.CompletedProcess(arguments, 0, ' - #0: right-index-finger\n', '')
            if arguments[0] == 'pam-auth-update':
                text = 'auth required pam_unix.so\n'
                if arguments[1] == '--enable':
                    text = 'auth sufficient pam_fprintd.so\n' + text
                auth.write_text(text)
            return self.command(arguments, **kwargs)
        with patch.object(vm, 'require_target'), patch.object(vm, 'require_reader'), \
                patch.object(vm, 'check_service'), patch.object(vm, 'run', side_effect=command):
            vm.set_login(True, 'test-user', True)
            self.assertTrue(vm.pam_has(auth.read_text(), 'pam_fprintd.so'))
            self.assertTrue((self.state / 'pam-enabled-by-verimark').exists())
            vm.set_login(False)
        self.assertTrue(vm.pam_has(auth.read_text(), 'pam_unix.so'))
        self.assertFalse(vm.pam_has(auth.read_text(), 'pam_fprintd.so'))
        self.assertFalse((self.state / 'pam-enabled-by-verimark').exists())

    def test_disable_leaves_existing_unmanaged_pam_alone(self):
        auth = self.pamdir / 'common-auth'
        text = 'auth sufficient pam_fprintd.so\nauth required pam_unix.so\n'
        auth.write_text(text)
        with patch.object(vm, 'require_target'), patch.object(vm, 'run') as command:
            vm.set_login(False)
            command.assert_not_called()
        self.assertEqual(auth.read_text(), text)

    def test_pairing_existing_state_is_reused_without_usb_commands(self):
        pairdir = self.root / 'pairdir'
        pairdir.mkdir()
        self.pairfile.parent.mkdir()
        self.pairfile.touch()
        upstream = self.root / '.build/sources/uriziel/tools'
        upstream.mkdir(parents=True)
        (upstream / 'verimark_pair.py').touch()
        # Directory owner checks use the real uid; fixture ownership is supplied explicitly.
        with patch.object(vm, 'require_target'), patch.object(vm, 'require_reader'), \
                patch.object(vm, 'private_file'), patch.object(vm, 'PAIRDIR', pairdir), \
                patch.object(vm, 'REPO', self.root), patch.object(Path, 'stat') as stat, \
                patch.object(Path, 'is_symlink', return_value=False), patch.object(Path, 'is_file', return_value=True), \
                patch.object(Path, 'exists', return_value=True), patch.object(vm, 'run') as command:
            stat.return_value.st_uid = 0
            stat.return_value.st_mode = 0o40700
            vm.pair(True)
            command.assert_not_called()

    def test_installer_restores_previous_library_on_service_failure(self):
        directory = self.artifact()
        self.library.mkdir(parents=True)
        (self.library / vm.LIBNAME).write_bytes(b'previous library')
        (self.library / 'libfprint-2.so.2').symlink_to(vm.LIBNAME)
        self.dropin.parent.mkdir()
        self.dropin.write_text(vm.DROPIN_TEXT)
        with patch.object(vm, 'require_target'), patch.object(vm, 'require_reader'), \
                patch.object(vm, 'private_file'), patch.object(vm, 'check_conflicts'), \
                patch.object(vm, 'validate_artifact', return_value=directory / vm.LIBNAME), \
                patch.object(vm, 'require_abi'), patch.object(vm, 'run', side_effect=self.command), \
                patch.object(vm, 'check_service', side_effect=vm.SetupError('startup failed')):
            with self.assertRaisesRegex(vm.SetupError, 'startup failed'):
                vm.install(directory)
        self.assertEqual((self.library / vm.LIBNAME).read_bytes(), b'previous library')
        self.assertEqual(self.dropin.read_text(), vm.DROPIN_TEXT)
        self.assertTrue((self.library / 'libfprint-2.so.2').is_symlink())

    def test_failed_first_install_restores_stock_configuration(self):
        directory = self.artifact()
        with patch.object(vm, 'require_target'), patch.object(vm, 'require_reader'), \
                patch.object(vm, 'private_file'), patch.object(vm, 'check_conflicts'), \
                patch.object(vm, 'validate_artifact', return_value=directory / vm.LIBNAME), \
                patch.object(vm, 'require_abi'), patch.object(vm, 'run', side_effect=self.command), \
                patch.object(vm, 'check_service', side_effect=vm.SetupError('startup failed')):
            with self.assertRaises(vm.SetupError):
                vm.install(directory)
        self.assertFalse(self.library.exists())
        self.assertFalse(self.dropin.exists())
        self.assertIn(['systemctl', 'restart', 'fprintd.service'], self.calls)

    def test_abi_failure_makes_no_system_changes(self):
        directory = self.artifact()
        with patch.object(vm, 'require_target'), patch.object(vm, 'require_reader'), \
                patch.object(vm, 'private_file'), patch.object(vm, 'check_conflicts'), \
                patch.object(vm, 'validate_artifact', return_value=directory / vm.LIBNAME), \
                patch.object(vm, 'require_abi', side_effect=vm.SetupError('ABI mismatch')), \
                patch.object(vm, 'run') as command:
            with self.assertRaisesRegex(vm.SetupError, 'ABI mismatch'):
                vm.install(directory)
            command.assert_not_called()
        self.assertFalse(self.dropin.exists())

    def test_rollback_preserves_pairing_and_unrelated_files(self):
        self.library.mkdir(parents=True)
        (self.library / vm.LIBNAME).write_bytes(b'fixture')
        (self.library / 'unrelated').write_text('preserve')
        self.dropin.parent.mkdir()
        self.dropin.write_text(vm.DROPIN_TEXT)
        self.pairfile.parent.mkdir()
        self.pairfile.write_bytes(b'private fixture')
        with patch.object(vm, 'require_target'), patch.object(vm, 'set_login'), \
                patch.object(vm, 'run', side_effect=self.command):
            vm.rollback()
        self.assertEqual(self.pairfile.read_bytes(), b'private fixture')
        self.assertEqual((self.library / 'unrelated').read_text(), 'preserve')
        self.assertFalse(self.dropin.exists())

    def test_rollback_refuses_modified_override(self):
        self.dropin.parent.mkdir()
        self.dropin.write_text('user changes')
        with patch.object(vm, 'require_target'), patch.object(vm, 'set_login'), \
                patch.object(vm, 'run') as command:
            with self.assertRaises(vm.SetupError):
                vm.rollback()
            command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
