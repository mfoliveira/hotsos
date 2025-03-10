from unittest import mock

from . import utils

from hotsos.core.config import setup_config
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.core.issues.utils import KnownBugsStore, IssuesStore
from hotsos.plugin_extensions.juju import summary

JOURNALCTL_CAPPEDPOSITIONLOST = """
Dec 21 14:07:53 juju-1 mongod.37017[17873]: [replication-18] CollectionCloner ns:juju.txns.log finished cloning with status: QueryPlanKilled: PlanExecutor killed: CappedPositionLost: CollectionScan died due to position in capped collection being deleted. Last seen record id: RecordId(204021366)
Dec 21 14:07:53 juju-1 mongod.37017[17873]: [replication-18] collection clone for 'juju.txns.log' failed due to QueryPlanKilled: While cloning collection 'juju.txns.log' there was an error 'PlanExecutor killed: CappedPositionLost: CollectionScan died due to position in capped collection being deleted. Last seen record id: RecordId(204021366)'
"""  # noqa

RABBITMQ_CHARM_LOGS = """
2021-02-17 08:18:44 ERROR juju.worker.dependency engine.go:671 "uniter" manifold worker returned unexpected error: failed to initialize uniter for "unit-rabbitmq-server-0": cannot create relation state tracker: cannot remove persisted state, relation 236 has members
2021-02-17 08:20:34 ERROR juju.worker.dependency engine.go:671 "uniter" manifold worker returned unexpected error: failed to initialize uniter for "unit-rabbitmq-server-0": cannot create relation state tracker: cannot remove persisted state, relation 236 has members
"""  # noqa

CONTROLLER_LOG1 = """
2022-06-22 09:23:40 ERROR juju.worker.migrationmaster.97cf4e worker.go:749 1 agents failed to report in time for "quiescing" phase (including machines: 61)
2022-06-22 09:23:40 ERROR juju.worker.migrationmaster.97cf4e worker.go:295 quiescing, timed out waiting for agents to report
2022-06-22 09:23:40 INFO juju.worker.migrationmaster.97cf4e worker.go:259 setting migration phase to ABORT
2022-06-22 09:23:40 INFO juju.worker.migrationmaster.97cf4e worker.go:295 aborted, removing model from target controller: quiescing, timed out waiting for agents to report
"""  # noqa

CONTROLLER_LOG2 = """
2022-08-01 08:19:35 INFO juju.worker.migrationmaster.97cf4e worker.go:295 aborted, removing model from target controller: model data transfer failed, failed to migrate binaries: charm local:bionic/ubuntu-12 unexpectedly assigned local:bionic/ubuntu-11
"""  # noqa

UNIT_LEADERSHIP_ERROR = """
2021-09-16 10:28:25 WARNING leader-elected ERROR cannot write leadership settings: cannot write settings: failed to merge leadership settings: application "keystone": prerequisites failed: "keystone/2" is not leader of "keystone"
2021-09-16 10:28:47 WARNING leader-elected ERROR cannot write leadership settings: cannot write settings: failed to merge leadership settings: application "keystone": prerequisites failed: "keystone/2" is not leader of "keystone"
2021-09-16 10:29:06 WARNING leader-elected ERROR cannot write leadership settings: cannot write settings: failed to merge leadership settings: application "keystone": prerequisites failed: "keystone/2" is not leader of "keystone"
2021-09-16 10:29:53 WARNING leader-elected ERROR cannot write leadership settings: cannot write settings: failed to merge leadership settings: application "keystone": prerequisites failed: "keystone/2" is not leader of "keystone"
2021-09-16 10:30:41 WARNING leader-elected ERROR cannot write leadership settings: cannot write settings: failed to merge leadership settings: application "keystone": prerequisites failed: "keystone/2" is not leader of "keystone"
"""  # noqa


UNKNOWN_RELATION_ERROR = """
2022-03-15 09:03:38 ERROR juju.worker.uniter agent.go:31 resolver loop error: unknown relation: 24
2022-03-15 09:03:38 INFO juju.worker.uniter uniter.go:309 unit "ams/0" shutting down: unknown relation: 24
2022-03-15 09:03:38 ERROR juju.worker.dependency engine.go:671 "uniter" manifold worker returned unexpected error: unknown relation: 24
"""  # noqa


KEYSTONE_SIMPLESTREAMS_ERROR = """
2022-04-19 21:32:42 WARNING unit.glance-simplestreams-sync/0.juju-log server.go:327 identity-service:317: Package openstack-release has no installation candidate.
2022-04-19 21:32:43 INFO unit.glance-simplestreams-sync/0.juju-log server.go:327 identity-service:317: Missing required data: internal_host internal_port
2022-04-19 21:32:43 INFO unit.glance-simplestreams-sync/0.juju-log server.go:327 identity-service:317: Missing required data: service_port service_host auth_host auth_port internal_host internal_port admin_tenant_name admin_user admin_password
2022-04-19 21:32:43 INFO unit.glance-simplestreams-sync/0.juju-log server.go:327 identity-service:317: Missing required data: internal_host internal_port
2022-04-19 21:32:43 INFO unit.glance-simplestreams-sync/0.juju-log server.go:327 identity-service:317: Loaded template from templates/identity.yaml
2022-04-19 21:32:43 INFO unit.glance-simplestreams-sync/0.juju-log server.go:327 identity-service:317: Rendering from template: /etc/glance-simplestreams-sync/identity.yaml
""" # noqa


class JujuTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        setup_config(PLUGIN_NAME='juju')


class TestJujuSummary(JujuTestsBase):

    def test_summary_keys(self):
        inst = summary.JujuSummary()
        self.assertEqual(list(inst.output.keys()),
                         ['charm-repo-info',
                          'charms',
                          'machine',
                          'services',
                          'units',
                          'version'])

    def test_service_info(self):
        expected = {'ps': ['jujud (1)'],
                    'systemd': {
                        'enabled': ['jujud-machine-1']}
                    }
        inst = summary.JujuSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['services'],
                         expected)

    def test_machine_info(self):
        inst = summary.JujuSummary()
        self.assertTrue(inst.plugin_runnable)
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['version'], '2.9.22')
        self.assertEqual(actual['machine'], '1')

    @mock.patch('hotsos.core.plugins.juju.resources.JujuMachine')
    def test_get_lxd_machine_info(self, mock_machine):
        mock_machine.return_value = mock.MagicMock()
        mock_machine.return_value.id = '0-lxd-11'
        mock_machine.return_value.version = '2.9.9'
        inst = summary.JujuSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['version'], '2.9.9')
        self.assertEqual(actual['machine'], '0-lxd-11')

    def test_charm_versions(self):
        expected = ['ceph-osd-508', 'neutron-openvswitch-457',
                    'nova-compute-589']
        inst = summary.JujuSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['charms'],
                         expected)

    def test_get_unit_info(self):
        expected = {'local': ['ceph-osd-0', 'neutron-openvswitch-1',
                              'nova-compute-0']}
        inst = summary.JujuSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['units'],
                         expected)


class TestJujuScenarios(JujuTestsBase):

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('juju_core_bugs.yaml'))
    @mock.patch('hotsos.core.ycheck.engine.properties.input.CLIHelper')
    def test_1852502(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_CAPPEDPOSITIONLOST.splitlines(keepends=True)

        YScenarioChecker()()
        mock_helper.return_value.journalctl.assert_called_with(
                                                            unit='juju-db')
        msg_1852502 = ('known mongodb bug identified - '
                       'https://jira.mongodb.org/browse/TOOLS-1636 '
                       'Workaround is to pass --no-logs to juju '
                       'create-backup. This is an issue only with Mongo '
                       '3. Mongo 4 does not have this issue. Upstream is '
                       'working on migrating to Mongo 4 in the Juju 3.0 '
                       'release.')
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1852502',
                      'desc': msg_1852502,
                      'origin': 'juju.01part'}]}
        self.assertEqual(KnownBugsStore().load(), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('juju_core_bugs.yaml'))
    @utils.create_test_files({'var/log/juju/unit-rabbitmq-server-0.log':
                              RABBITMQ_CHARM_LOGS,
                              'sos_commands/date/date':
                              'Thu Feb 10 16:19:17 UTC 2022'})
    def test_1910958(self):
        YScenarioChecker()()
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1910958',
                      'desc':
                      ('Unit unit-rabbitmq-server-0 failed to start due '
                       'to members in relation 236 that cannot be '
                       'removed.'),
                      'origin': 'juju.01part'}]}
        self.assertEqual(KnownBugsStore().load(), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('juju_core_bugs.yaml'))
    @utils.create_test_files({'var/log/juju/machine-2.log': CONTROLLER_LOG1,
                              'sos_commands/date/date':
                              'Wed Jun 22 09:00:00 UTC 2022'})
    def test_1983140(self):
        YScenarioChecker()()
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1983140',
                      'desc':
                      ('model migration failed - see LP bug for workaround.'),
                      'origin': 'juju.01part'}]}
        self.assertEqual(KnownBugsStore().load(), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('juju_core_bugs.yaml'))
    @utils.create_test_files({'var/log/juju/machine-2.log': CONTROLLER_LOG2,
                              'sos_commands/date/date':
                              'Mon Aug 01 08:00:00 UTC 2022'})
    def test_1983506(self):
        YScenarioChecker()()
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1983506',
                      'desc':
                      ('model migration failed - see LP bug for workaround.'),
                      'origin': 'juju.01part'}]}
        self.assertEqual(KnownBugsStore().load(), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('jujud_checks.yaml'))
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.processes',
                {})
    def test_jujud_checks(self):
        YScenarioChecker()()
        msg = ('No jujud processes found running on this host but it seems '
               'there should be since Juju is installed.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.properties.search.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('charm_checks.yaml'))
    @utils.create_test_files({'var/log/juju/unit-keystone-2.log':
                              UNIT_LEADERSHIP_ERROR})
    def test_unit_checks(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        # first try outside age limit
        mock_cli.return_value.date.return_value = "2021-09-25 00:00:00"
        YScenarioChecker()()
        self.assertEqual(IssuesStore().load(), {})

        # then within
        mock_cli.return_value.date.return_value = "2021-09-17 00:00:00"
        YScenarioChecker()()
        msg = ("Juju unit(s) 'keystone' are showing leadership errors in "
               "their logs from the last 7 days. Please investigate.")
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('juju_core_bugs.yaml'))
    @utils.create_test_files({'var/log/juju/unit-keystone-2.log':
                              UNKNOWN_RELATION_ERROR,
                              # make sure we are within the date constraints
                              'sos_commands/date/date':
                              'Thu Mar 15 00:00:00 UTC 2022'})
    def test_unknown_relation_bug(self):
        YScenarioChecker()()
        msg = ('One or more charms on this host has "unknown relation" '
               'errors which is an indication of this bug. Upgrading Juju '
               'to a version >= 2.9.13 should fix the problem.')
        issues = list(KnownBugsStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('charms_bugs.yaml'))
    @utils.create_test_files(
        {'var/log/juju/unit-glance-simplestreams-sync-0.log':
         KEYSTONE_SIMPLESTREAMS_ERROR,
         # make sure we are within the date constraints
         'sos_commands/date/date': 'Tue Apr 19 00:00:00 UTC 2022'})
    def test_keystone_simplestream_bug(self):
        YScenarioChecker()()
        msg = (
            'known glance-simplestream-sync bug identified - this happens '
            'because the relation data received from keystone does not have '
            'some of the expected data (internal_host and internal_port). '
            'Upgrading charm-keystone to version >= stable/539 should fix the '
            'problem.')
        bugs = list(KnownBugsStore().load().values())

        issues = []
        if len(bugs) > 0:
            issues = bugs[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])
