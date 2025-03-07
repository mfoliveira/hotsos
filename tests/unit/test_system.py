import os
import shutil
import tempfile

from unittest import mock

from . import utils

from hotsos.core.config import setup_config, HotSOSConfig
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.core.issues.utils import IssuesManager, IssuesStore
from hotsos.core.plugins.system.system import NUMAInfo
from hotsos.plugin_extensions.system import (
    checks,
    summary,
)

NUMACTL = """
available: 2 nodes (0-1)
node 0 cpus: 0 2 4 6 8 10 12 14 16 18 20 22 24 26 28 30 32 34 36 38
node 0 size: 96640 MB
node 0 free: 72733 MB
node 1 cpus: 1 3 5 7 9 11 13 15 17 19 21 23 25 27 29 31 33 35 37 39
node 1 size: 96762 MB
node 1 free: 67025 MB
node distances:
node   0   1
  0:  10  21
  1:  21  10
""".splitlines(keepends=True)  # noqa


class SystemTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        setup_config(PLUGIN_NAME='system')


class TestSystemSummary(SystemTestsBase):

    def test_get_service_info(self):
        expected = {'date': 'Thu Feb 10 16:19:17 UTC 2022',
                    'load': '3.58, 3.27, 2.58',
                    'hostname': 'compute4',
                    'num-cpus': 2,
                    'os': 'ubuntu focal',
                    'rootfs': ('/dev/vda2      308585260 25514372 267326276 '
                               '  9% /'),
                    'virtualisation': 'kvm',
                    'unattended-upgrades': 'ENABLED'}
        inst = summary.SystemSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, expected)


class TestNUMAInfo(SystemTestsBase):

    @mock.patch('hotsos.core.plugins.system.system.CLIHelper')
    def test_numainfo(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.numactl.return_value = NUMACTL
        nodes = {0: [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30,
                     32, 34, 36, 38],
                 1: [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31,
                     33, 35, 37, 39]}
        info = NUMAInfo()
        self.assertEqual(info.nodes, nodes)
        self.assertEqual(info.cores(0), nodes[0])
        self.assertEqual(info.cores(1), nodes[1])
        self.assertEqual(info.cores(), nodes[0] + nodes[1])


class TestSYSCtlChecks(SystemTestsBase):

    def test_sysctl_checks(self):
        expected = {'juju-charm-sysctl-mismatch': {
                        'kernel.pid_max': {
                            'conf': '50-ceph-osd-charm.conf',
                            'actual': '4194304',
                            'expected': '2097152'}}}
        inst = checks.SYSCtlChecks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, expected)

    def test_sysctl_checks_w_issue(self):
        expected = {'sysctl-mismatch': {
                        'kernel.pid_max': {
                            'actual': '4194304',
                            'expected': '12345678'}},
                    'juju-charm-sysctl-mismatch': {
                        'kernel.pid_max': {
                            'conf': '50-ceph-osd-charm.conf',
                            'actual': '4194304',
                            'expected': '2097152'}}}
        with tempfile.TemporaryDirectory() as dtmp:
            orig_data_root = HotSOSConfig.DATA_ROOT
            setup_config(DATA_ROOT=dtmp)
            os.makedirs(os.path.join(dtmp, 'etc'))
            etc_sysctl_conf = os.path.join(orig_data_root, 'etc/sysctl.conf')
            etc_sysctl_d = os.path.join(orig_data_root, 'etc/sysctl.d')
            shutil.copy(etc_sysctl_conf, os.path.join(dtmp, 'etc'))
            etc_sysctl_conf = os.path.join(dtmp, 'etc/sysctl.conf')
            shutil.copytree(etc_sysctl_d, os.path.join(dtmp, 'etc/sysctl.d'))
            shutil.copytree(os.path.join(orig_data_root, 'usr/lib/sysctl.d'),
                            os.path.join(dtmp, 'usr/lib/sysctl.d'))
            os.makedirs(os.path.join(dtmp, 'sos_commands'))
            shutil.copytree(os.path.join(orig_data_root,
                                         'sos_commands/kernel'),
                            os.path.join(dtmp, 'sos_commands/kernel'))

            with open(etc_sysctl_conf, 'a') as fd:
                fd.write('-net.core.rmem_default\n')

            # create a config with an unsetter
            with open(os.path.join(dtmp, 'etc/sysctl.d/99-unit-test.conf'),
                      'w') as fd:
                fd.write("-net.ipv4.conf.all.rp_filter\n")

            # create a config that has not been applied
            with open(os.path.join(dtmp, 'etc/sysctl.d/98-unit-test.conf'),
                      'w') as fd:
                fd.write("kernel.pid_max = 12345678\n")
                fd.write("net.ipv4.conf.all.rp_filter = 200\n")

            # inject an unset value into an invalid file
            with open(os.path.join(dtmp, 'etc/sysctl.d/97-unit-test.conf.bak'),
                      'w') as fd:
                fd.write("kernel.watchdog = 0\n")

            # create a config with an unsetter that wont be applied since it
            # has a lesser priority.
            with open(os.path.join(dtmp, 'etc/sysctl.d/96-unit-test.conf'),
                      'w') as fd:
                fd.write("-kernel.pid_max\n")
                fd.write("net.core.rmem_default = 1000000000\n")

            inst = checks.SYSCtlChecks()
            actual = self.part_output_to_actual(inst.output)
            self.assertEqual(actual, expected)


class TestSystemScenarioChecks(SystemTestsBase):

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('unattended_upgrades.yaml'))
    @mock.patch('hotsos.core.plugins.system.system.SystemBase.'
                'unattended_upgrades_enabled', True)
    @mock.patch('hotsos.core.plugins.system.SystemChecksBase.plugin_runnable',
                True)
    def test_unattended_upgrades(self):
        YScenarioChecker()()
        msg = ('Unattended upgrades are enabled which can lead to '
               'uncontrolled changes to this environment. If maintenance '
               'windows are required please consider disabling unattended '
               'upgrades.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @utils.create_test_files({'var/log/kern.log': 'Jun  4 06:25:10 host-name\
                                 kernel: [47841183.622537] lxcfs[1925937]:\
                                 segfault at 0 ip 00007f1ba005d4ea sp \
                                00007f1b7cfc1b10 error 4 in liblxcfs.so\
                                [7f1ba0055000+f000]',
                              'sos_commands/dpkg/dpkg_-l': 'ii  lxcfs \
                                3.0.3-0ubuntu1~18.04.1 \
                                amd64        FUSE based filesystem \
                                for LXC'})
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('lxcfs.yaml'))
    def test_lxcfs_segfault(self):
        YScenarioChecker()()
        msg = ('Segfault detected in LXCFS, LXD/LXC containers will likely'
               ' need to be restarted. The "lxcfs" package should be '
               'upgraded immediately to version 3.0.3-0ubuntu1~18.04.3'
               ' or better.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

        msg = ("Installed package 'lxcfs' with version 3.0.3-0ubuntu1~18.04.1"
               ' has a known critical bug which causes segfaults. '
               'If this environment is using LXD it should be '
               'upgraded ASAP.')
        issues = list(IssuesManager().load_bugs().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])
