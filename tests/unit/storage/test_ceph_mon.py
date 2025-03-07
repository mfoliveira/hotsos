import os

from unittest import mock
import json

from .. import utils

from hotsos.core.issues import IssuesManager
from hotsos.core.config import setup_config, HotSOSConfig
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.core.host_helpers.systemd import SystemdService
from hotsos.core.plugins.storage import (
    ceph as ceph_core,
)
from hotsos.plugin_extensions.storage import ceph_summary, ceph_event_checks

MON_ELECTION_LOGS = """
2022-01-02 06:24:23.876485 mon.test mon.1 10.230.16.55:6789/0 16486802 : cluster [INF] mon.test calling monitor election
2022-02-02 06:25:23.876485 mon.test mon.1 10.230.16.55:6789/0 16486802 : cluster [INF] mon.test calling monitor election
2022-02-02 06:26:23.876485 mon.test mon.1 10.230.16.55:6789/0 16486802 : cluster [INF] mon.test calling monitor election
2022-02-02 06:27:23.876485 mon.test mon.1 10.230.16.55:6789/0 16486802 : cluster [INF] mon.test calling monitor election
2022-02-02 06:28:23.876485 mon.test mon.1 10.230.16.55:6789/0 16486802 : cluster [INF] mon.test calling monitor election
2022-02-02 06:29:23.876485 mon.test mon.1 10.230.16.55:6789/0 16486802 : cluster [INF] mon.test calling monitor election
"""  # noqa

OSD_SLOW_HEARTBEATS = """
2022-03-16T07:30:00.004691+0000 mon.USC01STMON002 (mon.0) 3887456 : cluster [WRN]     Slow OSD heartbeats on back from osd.304 [] to osd.166 [] 525665.238 msec
2022-03-16T07:30:00.004702+0000 mon.USC01STMON002 (mon.0) 3887457 : cluster [WRN]     Slow OSD heartbeats on back from osd.46 [] to osd.28 [] 524753.655 msec
2022-03-16T07:30:00.004718+0000 mon.USC01STMON002 (mon.0) 3887458 : cluster [WRN]     Slow OSD heartbeats on back from osd.278 [] to osd.407 [] (down) 523734.980 msec
2022-03-16T07:30:00.004740+0000 mon.USC01STMON002 (mon.0) 3887459 : cluster [WRN]     Slow OSD heartbeats on back from osd.42 [] to osd.119 [] 523728.751 msec
2022-03-16T07:30:00.004760+0000 mon.USC01STMON002 (mon.0) 3887460 : cluster [WRN]     Slow OSD heartbeats on back from osd.172 [] to osd.21 [] 522972.419 msec
2022-03-16T07:30:00.004785+0000 mon.USC01STMON002 (mon.0) 3887461 : cluster [WRN]     Slow OSD heartbeats on back from osd.148 [] to osd.405 [] (down) 522698.150 msec
2022-03-16T07:30:00.004806+0000 mon.USC01STMON002 (mon.0) 3887462 : cluster [WRN]     Slow OSD heartbeats on back from osd.114 [] to osd.172 [] 521942.574 msec
2022-03-16T07:30:00.004832+0000 mon.USC01STMON002 (mon.0) 3887463 : cluster [WRN]     Slow OSD heartbeats on back from osd.287 [] to osd.139 [] (down) 521727.982 msec
2022-03-16T07:30:00.004850+0000 mon.USC01STMON002 (mon.0) 3887464 : cluster [WRN]     Slow OSD heartbeats on back from osd.356 [] (down) to osd.228 [] 520970.218 msec
2022-03-16T07:30:00.004861+0000 mon.USC01STMON002 (mon.0) 3887465 : cluster [WRN]     Slow OSD heartbeats on back from osd.355 [] to osd.81 [] 519784.959 msec
"""  # noqa

OSD_SLOW_OPS = """
2022-03-18T18:36:14.293172+0000 mon.juju-a79b06-10-lxd-0 (mon.0) 9766581 : cluster [WRN] Health check update: 3 slow ops, oldest one blocked for 65 sec, daemons [osd.12,osd.22,osd.6] have slow ops. (SLOW_OPS)
2022-03-18T18:36:19.295103+0000 mon.juju-a79b06-10-lxd-0 (mon.0) 9766590 : cluster [WRN] Health check update: 0 slow ops, oldest one blocked for 41 sec, daemons [osd.12,osd.13] have slow ops. (SLOW_OPS)
2022-03-18T18:36:24.296782+0000 mon.juju-a79b06-10-lxd-0 (mon.0) 9766593 : cluster [WRN] Health check update: 1 slow ops, oldest one blocked for 45 sec, daemons [osd.12,osd.13] have slow ops. (SLOW_OPS)
2022-03-18T18:36:29.298882+0000 mon.juju-a79b06-10-lxd-0 (mon.0) 9766603 : cluster [WRN] Health check update: 2 slow ops, oldest one blocked for 51 sec, daemons [osd.12,osd.13] have slow ops. (SLOW_OPS)
"""  # noqa

OSD_FLAPPING = """
2022-03-16T05:16:05.663450+0000 7fa713903700  0 log_channel(cluster) log [WRN] : Monitor daemon marked osd.70 down, but it is still running
2022-03-16T05:16:05.663454+0000 7fa713903700  0 log_channel(cluster) log [DBG] : map e319481 wrongly marked me down at e319481
"""  # noqa

CEPH_VERSIONS_MISMATCHED_MAJOR = """
{
    "mon": {
        "ceph version 15.2.13 (c44bc49e7a57a87d84dfff2a077a2058aa2172e2) octopus (stable)": 1
    },
    "mgr": {
        "ceph version 15.2.13 (c44bc49e7a57a87d84dfff2a077a2058aa2172e2) octopus (stable)": 1
    },
    "osd": {
        "ceph version 15.2.13 (c44bc49e7a57a87d84dfff2a077a2058aa2172e2) octopus (stable)": 2,
        "ceph version 14.2.18 (b77bc49e3a57a87d84df112a087a2058aa217118) nautilus (stable)": 1
    },
    "mds": {},
    "overall": {
        "ceph version 15.2.13 (c44bc49e7a57a87d84dfff2a077a2058aa2172e2) octopus (stable)": 5
    }
}
"""  # noqa


CEPH_VERSIONS_MISMATCHED_MINOR_MONS_UNALIGNED = """
{
    "mon": {
        "ceph version 15.2.11 (e3523634d9c2227df9af89a4eac33d16738c49cb) octopus (stable)": 3
        "ceph version 15.2.10 (1d69545544ae30333407eefa48e-b696b18994bf) octopus (stable)": 3
    },
    "mgr": {
        "ceph version 15.2.11 (e3523634d9c2227df9af89a4eac33d16738c49cb) octopus (stable)": 3
    },
    "osd": {
        "ceph version 15.2.11 (e3523634d9c2227df9af89a4eac33d16738c49cb) octopus (stable)": 208,
        "ceph version 15.2.13 (c44bc49e7a57a87d84dfff2a077a2058aa2172e2) octopus (stable)": 16
    },
    "mds": {},
    "overall": {
        "ceph version 15.2.11 (e3523634d9c2227df9af89a4eac33d16738c49cb) octopus (stable)": 217,
        "ceph version 15.2.13 (c44bc49e7a57a87d84dfff2a077a2058aa2172e2) octopus (stable)": 16
    }
}
"""  # noqa

CEPH_VERSIONS_MISMATCHED_MINOR = """
{
    "mon": {
        "ceph version 15.2.11 (e3523634d9c2227df9af89a4eac33d16738c49cb) octopus (stable)": 3
    },
    "mgr": {
        "ceph version 15.2.11 (e3523634d9c2227df9af89a4eac33d16738c49cb) octopus (stable)": 3
    },
    "osd": {
        "ceph version 15.2.11 (e3523634d9c2227df9af89a4eac33d16738c49cb) octopus (stable)": 208,
        "ceph version 15.2.13 (c44bc49e7a57a87d84dfff2a077a2058aa2172e2) octopus (stable)": 16
    },
    "mds": {},
    "overall": {
        "ceph version 15.2.11 (e3523634d9c2227df9af89a4eac33d16738c49cb) octopus (stable)": 217,
        "ceph version 15.2.13 (c44bc49e7a57a87d84dfff2a077a2058aa2172e2) octopus (stable)": 16
    }
}
"""  # noqa


CEPH_OSD_CRUSH_DUMP = """
{
        "buckets": [
            {
                "id": -1,
                "name": "default",
                "type_id": 11,
                "type_name": "root",
                "weight": 1926,
                "alg": "straw2",
                "hash": "rjenkins1",
                "items": [
                    {
                        "id": -3,
                        "weight": 642,
                        "pos": 0
                    },
                    {
                        "id": -5,
                        "weight": 642,
                        "pos": 1
                    },
                    {
                        "id": -7,
                        "weight": 642,
                        "pos": 2
                    }
                ]
            },
            {
                "id": -3,
                "name": "juju-94442c-oct00-1",
                "type_id": 1,
                "type_name": "host",
                "weight": 642,
                "alg": "straw2",
                "hash": "rjenkins1",
                "items": [
                    {
                        "id": 1,
                        "weight": 642,
                        "pos": 0
                    }
                ]
            },
            {
                "id": -5,
                "name": "juju-94442c-oct00-3",
                "type_id": 1,
                "type_name": "host",
                "weight": 642,
                "alg": "straw2",
                "hash": "rjenkins1",
                "items": [
                    {
                        "id": 0,
                        "weight": 642,
                        "pos": 0
                    }
                ]
            },
            {
                "id": -7,
                "name": "juju-94442c-oct00-2",
                "type_id": 3,
                "type_name": "rack00",
                "weight": 642,
                "alg": "straw2",
                "hash": "rjenkins1",
                "items": [
                    {
                        "id": 2,
                        "weight": 642,
                        "pos": 0
                    }
                ]
            }
        ]
    }
"""

PG_DUMP_JSON_DECODED = {'pg_map': {
                          'pg_stats': [
                            {'stat_sum': {'num_large_omap_objects': 1},
                             'last_scrub_stamp': '2021-09-16T21:26:00.00',
                             'last_deep_scrub_stamp': '2021-09-16T21:26:00.00',
                             'pgid': '2.f',
                             'state': 'active+clean+laggy'}]}}


CEPH_MON_DATA_ROOT = os.path.join(utils.TESTS_DIR,
                                  'fake_data_root/storage/ceph-mon')
CEPH_REPORT = os.path.join(CEPH_MON_DATA_ROOT,
                           'sos_commands/ceph_mon/ceph_report')
# this file has been added for test purposes
CEPH_OSD_CRUSH_DUMP_UNBALANCED = os.path.join(CEPH_MON_DATA_ROOT,
                                              'sos_commands/ceph_mon/'
                                              'ceph_osd_crush_dump.'
                                              'unbalanced')


class StorageCephMonTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        setup_config(DATA_ROOT=CEPH_MON_DATA_ROOT, PLUGIN_NAME='storage',
                     MACHINE_READABLE=True)

    def setup_fake_cli_osds_imbalanced_pgs(self, mock_cli_helper):
        """
        Mocks ceph osd df tree so that it contains OSDs with imbalanced PGs.

        Returns a dictionary used to match the output of the storage.ceph
        plugin i.e. the summary output.
        """
        inst = mock.MagicMock()
        mock_cli_helper.return_value = inst
        out = {'nodes': [{'id': 0, 'pgs': 295, 'name': "osd.0"},
                         {'id': 1, 'pgs': 501, 'name': "osd.1"},
                         {'id': 2, 'pgs': 200, 'name': "osd.2"}]}
        inst.ceph_osd_df_tree_json_decoded.return_value = out

        return {'osd-pgs-suboptimal': {
                    'osd.0': 295,
                    'osd.1': 501},
                'osd-pgs-near-limit': {
                     'osd.1': 501}}


class TestCoreCephCluster(StorageCephMonTestsBase):

    def test_cluster_mons(self):
        cluster_mons = ceph_core.CephCluster().mons
        self.assertEqual([ceph_core.CephMon],
                         list(set([type(obj) for obj in cluster_mons])))

    def test_cluster_osds(self):
        cluster_osds = ceph_core.CephCluster().osds
        self.assertEqual([ceph_core.CephOSD],
                         list(set([type(obj) for obj in cluster_osds])))

    def test_health_status(self):
        health = ceph_core.CephCluster().health_status
        self.assertEqual(health, 'HEALTH_WARN')

    def test_osd_versions(self):
        versions = ceph_core.CephCluster().daemon_versions('osd')
        self.assertEqual(versions, {'15.2.14': 3})

    def test_mon_versions(self):
        versions = ceph_core.CephCluster().daemon_versions('mon')
        self.assertEqual(versions, {'15.2.14': 3})

    def test_mds_versions(self):
        versions = ceph_core.CephCluster().daemon_versions('mds')
        self.assertEqual(versions, {})

    def test_rgw_versions(self):
        versions = ceph_core.CephCluster().daemon_versions('rgw')
        self.assertEqual(versions, {})

    def test_osd_release_name(self):
        release_names = ceph_core.CephCluster().daemon_release_names('osd')
        self.assertEqual(release_names, {'octopus': 3})

    def test_mon_release_name(self):
        release_names = ceph_core.CephCluster().daemon_release_names('mon')
        self.assertEqual(release_names, {'octopus': 3})

    def test_cluster_osd_ids(self):
        cluster = ceph_core.CephCluster()
        self.assertEqual([osd.id for osd in cluster.osds], [0, 1, 2])

    def test_crush_rules(self):
        cluster = ceph_core.CephCluster()
        expected = {'replicated_rule': {'id': 0, 'type': 'replicated',
                    'pools': ['device_health_metrics (1)', 'glance (2)',
                              'cinder-ceph (3)', 'nova (4)']}}
        self.assertEqual(cluster.crush_map.rules, expected)

    def test_ceph_daemon_versions_unique(self):
        result = {'mgr': ['15.2.14'],
                  'mon': ['15.2.14'],
                  'osd': ['15.2.14']}
        cluster = ceph_core.CephCluster()
        self.assertEqual(cluster.ceph_daemon_versions_unique(), result)
        self.assertTrue(cluster.ceph_versions_aligned)
        self.assertTrue(cluster.mon_versions_aligned_with_cluster)

    @utils.create_test_files({'sos_commands/ceph_mon/ceph_versions':
                              CEPH_VERSIONS_MISMATCHED_MINOR_MONS_UNALIGNED})
    def test_ceph_daemon_versions_unique_not(self):
        result = {'mgr': ['15.2.11'],
                  'mon': ['15.2.11',
                          '15.2.10'],
                  'osd': ['15.2.11',
                          '15.2.13']}
        cluster = ceph_core.CephCluster()
        self.assertEqual(cluster.ceph_daemon_versions_unique(), result)
        self.assertFalse(cluster.ceph_versions_aligned)
        self.assertFalse(cluster.mon_versions_aligned_with_cluster)

    @utils.create_test_files({'sos_commands/ceph_mon/ceph_osd_crush_dump':
                              open(CEPH_OSD_CRUSH_DUMP_UNBALANCED).read(),
                              'sos_commands/ceph_mon/ceph_report':
                              open(CEPH_REPORT).read()})
    def test_check_crushmap_non_equal_buckets(self):
        cluster = ceph_core.CephCluster()
        buckets = cluster.crush_map.crushmap_equal_buckets
        self.assertEqual(buckets,
                         ["tree 'default' at the 'rack' level"])

    def test_crushmap_equal_buckets(self):
        cluster = ceph_core.CephCluster()
        buckets = cluster.crush_map.crushmap_equal_buckets
        self.assertEqual(buckets, [])

    @utils.create_test_files({'sos_commands/ceph_mon/ceph_osd_crush_dump':
                              CEPH_OSD_CRUSH_DUMP})
    def test_crushmap_mixed_buckets(self):
        cluster = ceph_core.CephCluster()
        buckets = cluster.crush_map.crushmap_mixed_buckets
        self.assertEqual(buckets, ['default'])

    def test_crushmap_no_mixed_buckets(self):
        cluster = ceph_core.CephCluster()
        buckets = cluster.crush_map.crushmap_mixed_buckets
        self.assertEqual(buckets, [])

    def test_mgr_modules(self):
        cluster = ceph_core.CephCluster()
        expected = ['balancer',
                    'crash',
                    'devicehealth',
                    'orchestrator',
                    'pg_autoscaler',
                    'progress',
                    'rbd_support',
                    'status',
                    'telemetry',
                    'volumes',
                    'iostat',
                    'restful']
        self.assertEqual(cluster.mgr_modules, expected)


class TestMonCephSummary(StorageCephMonTestsBase):

    def test_get_service_info(self):
        svc_info = {'systemd': {'enabled': [
                                    'ceph-crash',
                                    'ceph-mgr',
                                    'ceph-mon',
                                    ],
                                'disabled': [
                                    'ceph-mds',
                                    'ceph-osd',
                                    'ceph-radosgw',
                                    'ceph-volume'
                                    ],
                                'generated': ['radosgw'],
                                'masked': ['ceph-create-keys']},
                    'ps': ['ceph-crash (1)', 'ceph-mgr (1)', 'ceph-mon (1)']}
        release_info = {'name': 'octopus', 'days-to-eol': 3000}
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['services'], svc_info)
        self.assertEqual(actual['release'], release_info)
        self.assertEqual(actual['status'], 'HEALTH_WARN')

    def test_get_network_info(self):
        expected = {'cluster': {
                        'eth0@if17': {
                            'addresses': ['10.0.0.123'],
                            'hwaddr': '00:16:3e:ae:9e:44',
                            'state': 'UP',
                            'speed': '10000Mb/s'}},
                    'public': {
                        'eth0@if17': {
                            'addresses': ['10.0.0.123'],
                            'hwaddr': '00:16:3e:ae:9e:44',
                            'state': 'UP',
                            'speed': '10000Mb/s'}}
                    }
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['network'], expected)

    def test_ceph_cluster_info(self):
        expected = {'crush-rules': {
                        'replicated_rule': {
                            'id': 0,
                            'pools': [
                                'device_health_metrics (1)',
                                'glance (2)',
                                'cinder-ceph (3)',
                                'nova (4)'],
                            'type': 'replicated'}},
                    'versions': {'mgr': ['15.2.14'],
                                 'mon': ['15.2.14'],
                                 'osd': ['15.2.14']}}
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['crush-rules'], expected['crush-rules'])
        self.assertEqual(actual['versions'], expected['versions'])

    @mock.patch('hotsos.core.plugins.storage.ceph.CephCluster.pool_id_to_name',
                lambda *args: 'foo')
    @utils.create_test_files({'sos_commands/ceph_mon/json_output/'
                              'ceph_pg_dump_--format_json-pretty':
                              json.dumps(PG_DUMP_JSON_DECODED)})
    def test_ceph_cluster_info_large_omap_pgs(self):
        expected = {'2.f': {
                        'pool': 'foo',
                        'last_scrub_stamp': '2021-09-16T21:26:00.00',
                        'last_deep_scrub_stamp': '2021-09-16T21:26:00.00'}}
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['large-omap-pgs'], expected)

    @mock.patch.object(ceph_core, 'CLIHelper')
    def test_get_ceph_pg_imbalance(self, mock_helper):
        result = self.setup_fake_cli_osds_imbalanced_pgs(mock_helper)
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['osd-pgs-suboptimal'],
                         result['osd-pgs-suboptimal'])
        self.assertEqual(actual['osd-pgs-near-limit'],
                         result['osd-pgs-near-limit'])

    @utils.create_test_files({'sos_commands/ceph_mon/json_output/'
                              'ceph_osd_df_tree_--format_json-pretty':
                              json.dumps([])})
    def test_get_ceph_pg_imbalance_unavailable(self):
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertFalse('osd-pgs-suboptimal' in actual)
        self.assertFalse('osd-pgs-near-limit' in actual)

    def test_get_ceph_versions(self):
        result = {'mgr': ['15.2.14'],
                  'mon': ['15.2.14'],
                  'osd': ['15.2.14']}
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['versions'], result)

    @utils.create_test_files({'sos_commands/ceph_mon/ceph_versions':
                              json.dumps([])})
    def test_get_ceph_versions_unavailable(self):
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertIsNone(actual.get('versions'))


class TestMonCephEventChecks(StorageCephMonTestsBase):

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('mon/monlogs.yaml'))
    def test_get_ceph_daemon_log_checker(self):
        result = {'osd-reported-failed': {'osd.41': {'2022-02-08': 23},
                                          'osd.85': {'2022-02-08': 4}},
                  'long-heartbeat-pings': {'2022-02-09': 4},
                  'heartbeat-no-reply': {'2022-02-09': {'osd.0': 1,
                                                        'osd.1': 2}}}
        inst = ceph_event_checks.CephDaemonLogChecks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, result)


class TestStorageScenarioChecksCephMon(StorageCephMonTestsBase):

    @utils.create_test_files({})
    def test_scenarios_none(self):
        YScenarioChecker()()
        issues = list(IssuesManager().load_issues().values())
        self.assertEqual(len(issues), 0)

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter(
                                       'ceph-mon/mon_elections_flapping.yaml'))
    @mock.patch('hotsos.core.plugins.storage.ceph.CephChecksBase')
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mon': SystemdService('ceph-mon', 'enabled')})
    @utils.create_test_files({'var/log/ceph/ceph.log': MON_ELECTION_LOGS})
    def test_scenario_mon_reelections(self, mock_cephbase):
        mock_cephbase.return_value = mock.MagicMock()
        mock_cephbase.return_value.plugin_runnable = True
        mock_cephbase.return_value.has_interface_errors = True
        mock_cephbase.return_value.bind_interface_names = 'ethX'
        YScenarioChecker()()
        msg = ('The Ceph monitor on this host has experienced 5 re-elections '
               'within a 24hr period and the network interface(s) ethX used '
               'by the ceph-mon are showing errors - please investigate.')

        # Since we have enabled machine readable we should get some context so
        # test that as well.
        logpath = os.path.join(HotSOSConfig.DATA_ROOT, 'var/log/ceph/ceph.log')
        context = {logpath: 2,
                   'ops': 'truth',
                   'passes': True,
                   'property': ('hotsos.core.plugins.storage.ceph.'
                                'CephChecksBase.has_interface_errors'),
                   'value_actual': True}

        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])
        self.assertEqual([issue['context'] for issue in issues], [context])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-mon/osd_slow_heartbeats.yaml'))
    @mock.patch('hotsos.core.plugins.storage.ceph.CephChecksBase')
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mon': SystemdService('ceph-mon', 'enabled')})
    @utils.create_test_files({'var/log/ceph/ceph.log': OSD_SLOW_HEARTBEATS})
    def test_scenario_osd_slow_heartbeats(self, mock_cephbase):
        mock_cephbase.return_value = mock.MagicMock()
        mock_cephbase.return_value.plugin_runnable = True
        YScenarioChecker()()
        msg = ("One or more Ceph OSDs is showing slow heartbeats. This most "
               "commonly a result of network issues between OSDs. Please "
               "check that the interfaces and network between OSDs is not "
               "experiencing problems.")
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-mon/bluefs_spillover.yaml'))
    @mock.patch('hotsos.core.ycheck.engine.properties.input.CLIHelper')
    @mock.patch('hotsos.core.plugins.storage.ceph.CephCluster.health_status',
                'HEALTH_WARN')
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mon': SystemdService('ceph-mon', 'enabled')})
    def test_scenario_bluefs_spillover(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ceph_health_detail_json_decoded.return_value \
            = " experiencing BlueFS spillover"

        YScenarioChecker()()
        msg = ('Identified known Ceph bug. RocksDB needs more space than the '
               'leveled space available. See '
               'www.mail-archive.com/ceph-users@ceph.io/msg05782.html '
               'for more background information.')
        issues = list(IssuesManager().load_bugs().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-mon/osd_slow_ops.yaml'))
    @mock.patch('hotsos.core.plugins.storage.ceph.CephChecksBase')
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mon': SystemdService('ceph-mon', 'enabled')})
    @utils.create_test_files({'var/log/ceph/ceph.log': OSD_SLOW_OPS})
    def test_scenario_osd_slow_ops(self, mock_cephbase):
        mock_cephbase.return_value = mock.MagicMock()
        mock_cephbase.return_value.plugin_runnable = True
        mock_cephbase.return_value.has_interface_errors = True
        mock_cephbase.return_value.bind_interface_names = 'ethX'
        YScenarioChecker()()
        msg = ("Cluster is experiencing slow ops. The network interface(s) "
               "(ethX) used by the Ceph are showing errors - please "
               "investigate.")

        # Since we have enabled machine readable we should get some context so
        # test that as well.
        logpath = os.path.join(HotSOSConfig.DATA_ROOT, 'var/log/ceph/ceph.log')
        context = {logpath: 5,
                   'ops': 'truth',
                   'passes': True,
                   'property': ('hotsos.core.plugins.storage.ceph.'
                                'CephChecksBase.has_interface_errors'),
                   'value_actual': True}

        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])
        self.assertEqual([issue['context'] for issue in issues], [context])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-mon/osd_flapping.yaml'))
    @mock.patch('hotsos.core.plugins.storage.ceph.CephChecksBase')
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mon': SystemdService('ceph-mon', 'enabled')})
    @utils.create_test_files({'var/log/ceph/ceph.log': OSD_FLAPPING})
    def test_scenario_osd_flapping(self, mock_cephbase):
        mock_cephbase.return_value = mock.MagicMock()
        mock_cephbase.return_value.plugin_runnable = True
        mock_cephbase.return_value.has_interface_errors = True
        mock_cephbase.return_value.bind_interface_names = 'ethX'
        YScenarioChecker()()
        msg = ("Cluster is experiencing OSD flapping. The network "
               "interface(s) (ethX) used by the Ceph are showing errors "
               "- please investigate.")

        # Since we have enabled machine readable we should get some context so
        # test that as well.
        logpath = os.path.join(HotSOSConfig.DATA_ROOT, 'var/log/ceph/ceph.log')
        context = {logpath: 3,
                   'ops': 'truth',
                   'passes': True,
                   'property': ('hotsos.core.plugins.storage.ceph.'
                                'CephChecksBase.has_interface_errors'),
                   'value_actual': True}

        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])
        self.assertEqual([issue['context'] for issue in issues], [context])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter(
                    'ceph-mon/osd_maps_backlog_too_large.yaml'))
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mon': SystemdService('ceph-mon', 'enabled')})
    @utils.create_test_files({'sos_commands/ceph_mon/ceph_report':
                              json.dumps({'osdmap_manifest':
                                          {'pinned_maps':
                                           list(range(5496))}})})
    def test_scenario_osd_maps_backlog_too_large(self):
        YScenarioChecker()()
        msg = ("This Ceph cluster has 5496 pinned osdmaps. This can affect "
               "ceph-mon performance and may also indicate bugs such as "
               "https://tracker.ceph.com/issues/44184 and "
               "https://tracker.ceph.com/issues/47290.")
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.storage.ceph.CephCluster.'
                'require_osd_release', 'octopus')
    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter(
                                'ceph-mon/required_osd_release_mismatch.yaml'))
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mon': SystemdService('ceph-mon', 'enabled')})
    @utils.create_test_files({'sos_commands/ceph_mon/ceph_versions':
                              CEPH_VERSIONS_MISMATCHED_MAJOR})
    def test_required_osd_release(self):
        YScenarioChecker()()
        msg = ("Ceph cluster config 'require_osd_release' is set to 'octopus' "
               "but not all OSDs are on that version - please check.")
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.storage.ceph.CephCluster.'
                'require_osd_release', 'octopus')
    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-mon/laggy_pgs.yaml'))
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mon': SystemdService('ceph-mon', 'enabled')})
    @utils.create_test_files({'sos_commands/ceph_mon/json_output/'
                              'ceph_pg_dump_--format_json-pretty':
                              json.dumps(PG_DUMP_JSON_DECODED)})
    def test_laggy_pgs(self):
        YScenarioChecker()()
        msg = ('Ceph cluster is reporting 1 laggy/wait PGs. This suggests a '
               'potential network or storage issue - please check.')
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.storage.ceph.CephCluster.health_status',
                'HEALTH_WARN')
    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-mon/ceph_cluster_health.yaml'))
    def test_ceph_cluster_health(self):
        YScenarioChecker()()
        msg = ("Ceph cluster is in 'HEALTH_WARN' state. Please check "
               "'ceph status' for details.")
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.storage.ceph.CephCluster.health_status',
                'HEALTH_OK')
    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-mon/ceph_cluster_health.yaml'))
    def test_ceph_cluster_health_ok(self):
        YScenarioChecker()()
        issues = list(IssuesManager().load_issues().values())
        self.assertEqual(len(issues), 0)

    @mock.patch('hotsos.core.plugins.storage.ceph.CephChecksBase.release_name',
                'nautilus')
    @mock.patch('hotsos.core.plugins.storage.ceph.CephCluster.'
                'cluster_osds_without_v2_messenger_protocol', ['osd.1'])
    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter(
                                    'ceph-mon/osd_messenger_v2_protocol.yaml'))
    def test_osd_messenger_v2_protocol(self):
        YScenarioChecker()()
        msg = ("This Ceph cluster has 1 OSD(s) that do not bind to a v2 "
               "messenger address. This will cause unexpected behaviour and "
               "should be resolved asap.")
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-mon/large_omap_objects.yaml'))
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mon': SystemdService('ceph-mon', 'enabled')})
    @utils.create_test_files({'sos_commands/ceph_mon/json_output/'
                              'ceph_pg_dump_--format_json-pretty':
                              json.dumps(PG_DUMP_JSON_DECODED)})
    def test_large_omap_objects(self):
        YScenarioChecker()()
        msg = ("Large omap objects found in pgs '2.f'. "
               "This is usually resolved by deep-scrubbing the pgs. Check "
               "config options "
               "'osd_deep_scrub_large_omap_object_key_threshold' and "
               "'osd_deep_scrub_large_omap_object_value_sum_threshold' to "
               "find whether the values of these keys are too high. "
               "See full summary for more detail.")
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-mon/bluefs_size.yaml'))
    def test_bluefs_size(self):
        YScenarioChecker()()
        msg = ("Found OSDs osd.0, osd.1, osd.2 with metadata usage > 5% "
               "of its total device usage. This could be the result of "
               "a compaction failure. Possibly related to the bug "
               "https://tracker.ceph.com/issues/45903 if Ceph < 14.2.17. "
               "To manually compact the metadata, use 'ceph-bluestore-tool' "
               "which is available since 14.2.0.")

        issues = list(IssuesManager().load_bugs().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter(
                                       'ceph-mon/ceph_versions_mismatch.yaml'))
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mon': SystemdService('ceph-mon', 'enabled')})
    @utils.create_test_files({'sos_commands/ceph_mon/ceph_versions':
                              CEPH_VERSIONS_MISMATCHED_MINOR})
    def test_ceph_versions_mismatch_p1(self):
        YScenarioChecker()()
        msg = ('Ceph daemon versions are not aligned across the cluster. This '
               'could be the result of an incomplete or failed cluster '
               'upgrade. All daemons, except the clients, should ideally be '
               'on the same version for ceph to function correctly.')
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter(
                                       'ceph-mon/ceph_versions_mismatch.yaml'))
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mon': SystemdService('ceph-mon', 'enabled')})
    @utils.create_test_files({'sos_commands/ceph_mon/ceph_versions':
                              CEPH_VERSIONS_MISMATCHED_MINOR_MONS_UNALIGNED})
    def test_ceph_versions_mismatch_p2(self):
        YScenarioChecker()()
        msg = ('One or more Ceph mons has a version lower than other daemons '
               'e.g. ceph-osd running in the cluster. This can cause '
               'unexpected behaviour and should be resolved as soon as '
               'possible. Check full summary output for current versions.')
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.storage.ceph.CLIHelper')
    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-mon/pg_imbalance.yaml'))
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mon': SystemdService('ceph-mon', 'enabled')})
    def test_ceph_pg_imbalance(self, mock_helper):
        self.setup_fake_cli_osds_imbalanced_pgs(mock_helper)
        YScenarioChecker()()
        msg1 = ('Found some Ceph osd(s) with > 500 pgs - this is close to the '
                'hard limit at which point they will stop creating pgs and '
                'fail - please investigate.')
        msg2 = ('Found some Ceph osd(s) whose pg count is > 30% outside the '
                'optimal range of 50-200 pgs. This could indicate poor data '
                'distribution across the cluster and result in '
                'performance degradation.')
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg1, msg2])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter(
                                       'ceph-mon/crushmap_bucket_checks.yaml'))
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mon': SystemdService('ceph-mon', 'enabled')})
    @utils.create_test_files({'sos_commands/ceph_mon/ceph_osd_crush_dump':
                              CEPH_OSD_CRUSH_DUMP,
                              'sos_commands/ceph_mon/ceph_report':
                              open(CEPH_REPORT).read()})
    def test_crushmap_bucket_checks_mixed_buckets(self):
        YScenarioChecker()()
        msg = ("Mixed crush bucket types identified in buckets 'default'. "
               "This can cause data distribution to become skewed - please "
               "check crush map.")
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter(
                                       'ceph-mon/crushmap_bucket_checks.yaml'))
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mon': SystemdService('ceph-mon', 'enabled')})
    @utils.create_test_files({'sos_commands/ceph_mon/ceph_osd_crush_dump':
                              open(CEPH_OSD_CRUSH_DUMP_UNBALANCED).read(),
                              'sos_commands/ceph_mon/ceph_report':
                              open(CEPH_REPORT).read()})
    def test_crushmap_bucket_checks_unbalanced_buckets(self):
        YScenarioChecker()()
        msg = ("Found one or more unbalanced buckets in the cluster's CRUSH "
               'map. This can cause uneven data distribution or PG mapping '
               'issues in the cluster. Verify that "ceph osd crush tree '
               '--show-shadow" conforms to the expected layout for the '
               'cluster. Transient issues such as "out" OSDs, or cluster '
               'expansion/maintenance can trigger this warning. Affected '
               'CRUSH tree(s) and bucket types are tree \'default\' at the '
               '\'rack\' level.')
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-mon/unresponsive_mon_mgr.yaml'))
    @mock.patch('hotsos.core.plugins.sosreport.SOSReportChecksBase.'
                'timed_out_plugins', ['ceph_mon'])
    @mock.patch('hotsos.core.host_helpers.APTPackageHelper.all',
                {'ceph-mon': '1.2.3'})
    def test_unresponsive_mgr_p1(self):
        YScenarioChecker()()
        msg = ("One or more sosreport ceph plugins contain incomplete data. "
               "This usually indicates a problem with ceph mon/mgr. Please "
               "check ceph-mon.log and retry commands to see if they are "
               "still unresponsive. Restarting ceph-mon and ceph-mgr might "
               "resolve this.")
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-mon/unresponsive_mon_mgr.yaml'))
    @mock.patch('hotsos.core.plugins.storage.ceph.CephCluster.osd_df_tree',
                None)
    @mock.patch('hotsos.core.plugins.sosreport.SOSReportChecksBase.'
                'plugin_runnable', False)
    @mock.patch('hotsos.core.host_helpers.APTPackageHelper.all',
                {'ceph-mon': '1.2.3'})
    def test_unresponsive_mgr_p2(self):
        YScenarioChecker()()
        msg = ("Some ceph commands are returning incomplete data. This "
               "usually indicates a problem with ceph mon/mgr. Please check "
               "ceph-mon.log and retry commands to see if they are still "
               "unresponsive. Restarting ceph-mon and ceph-mgr might "
               "resolve this.")

        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-mon/eol.yaml'))
    @mock.patch('hotsos.core.host_helpers.cli.DateFileCmd.format_date')
    def test_ceph_mon_eol(self, mock_date):
        # 2030-04-30
        mock_date.return_value = '1903748400'

        YScenarioChecker()()
        issues = list(IssuesManager().load_issues().values())[0]

        expected = ('This node is running a version of Ceph that is '
                    'End of Life (release=octopus) which means it '
                    'has limited support and is likely not receiving '
                    'updates anymore. Please consider upgrading to a '
                    'newer release.')

        self.assertEqual(issues[0]['desc'], expected)
