from datetime import datetime
import os
import glob

import re

from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.utils import cached_property, sorted_dict

SVC_EXPR_TEMPLATES = {
    "absolute": r".+\S+bin/({})(?:\s+.+|$)",
    "snap": r".+\S+\d+/({})(?:\s+.+|$)",
    "relative": r".+\s({})(?:\s+.+|$)",
    }


class SystemdService(object):

    def __init__(self, name, state):
        self.name = name
        self.state = state
        self._start_time = None

    @property
    def start_time(self):
        """ Get most recent start time of this service unit.

        @returns: datetime.datetime object or None if time not found.
        """
        if self._start_time:
            return self._start_time

        cexpr = re.compile(r"^(([0-9-]+)T[\d:]+\+[\d]+)\s+.+: "
                           "(Started|Starting) .+")
        journal = CLIHelper().journalctl(unit=self.name)
        last = None
        for line in journal:
            ret = cexpr.search(line)
            if ret:
                last = ret.group(1)

        if last:
            self._start_time = datetime.strptime(last, "%Y-%m-%dT%H:%M:%S+%f")

        return self._start_time


class SystemdHelper(object):
    """This class should be used by any plugin that wants to identify
    and check the status of running services."""

    def __init__(self, service_exprs, ps_allow_relative=True):
        """
        @param service_exprs: list of python.re expressions used to match a
        service name.
        @param ps_allow_relative: whether to allow commands to be identified
                                  from ps as not run using an absolute binary
                                  path e.g. mycmd as opposed to /bin/mycmd.
        """
        self._ps_allow_relative = ps_allow_relative
        self._service_exprs = set(service_exprs)

    @cached_property
    def _systemctl_list_units(self):
        return CLIHelper().systemctl_list_units()

    @cached_property
    def _ps(self):
        return CLIHelper().ps()

    def _get_systemd_units(self, expr):
        """
        Search systemd unit instances.

        @param expr: expression used to match one or more units in --list-units
        """
        units = []
        for line in self._systemctl_list_units:
            ret = re.compile(expr).match(line)
            if ret:
                units.append(ret.group(1))

        return units

    @cached_property
    def services(self):
        """
        Return a dict of identified systemd services and their state.

        Services are represented as either direct or indirect units and
        typically use one or the other. We homongenise these to present state
        based on the one we think is being used. Enabled units are aggregated
        but masked units are not so that they can be identified and reported.
        """
        svc_info = {}
        indirect_svc_info = {}
        for line in CLIHelper().systemctl_list_unit_files():
            for expr in self._service_exprs:
                # Add snap prefix/suffixes
                base_expr = r"(?:snap\.)?{}(?:\.daemon)?".format(expr)
                # NOTE: we include indirect services (ending with @) so that
                #       we can search for related units later.
                unit_expr = r'^\s*({}(?:@\S*)?)\.service'.format(base_expr)
                # match entries in systemctl list-unit-files
                unit_files_expr = r'{}\s+(\S+)'.format(unit_expr)

                ret = re.compile(unit_files_expr).match(line)
                if ret:
                    unit = ret.group(1)
                    state = ret.group(2)
                    if unit.endswith('@'):
                        # indirect or "template" units can have "instantiated"
                        # units where only the latter represents whether the
                        # unit is in use. If an indirect unit has instanciated
                        # units we use them to represent the state of the
                        # service.
                        unit_svc_expr = r"\s+({}\d*)".format(unit)
                        unit = unit.partition('@')[0]
                        if self._get_systemd_units(unit_svc_expr):
                            state = 'enabled'

                        indirect_svc_info[unit] = state
                    else:
                        svc_info[unit] = SystemdService(unit, state)

        if indirect_svc_info:
            # Allow indirect unit info to override given certain conditions
            for unit, state in indirect_svc_info.items():
                if unit in svc_info:
                    if state == 'disabled' or svc_info[unit] == 'enabled':
                        continue

                    svc_info[unit].state = state
                else:
                    svc_info[unit] = SystemdService(unit, state)

        return svc_info

    @property
    def masked_services(self):
        """ Returns a list of masked services. """
        if not self.services:
            return []

        return self._service_info.get('masked', [])

    def get_process_cmd_from_line(self, line, expr):
        for expr_type, expr_tmplt in SVC_EXPR_TEMPLATES.items():
            if expr_type == 'relative' and not self._ps_allow_relative:
                continue

            ret = re.compile(expr_tmplt.format(expr)).match(line)
            if ret:
                svc = ret.group(1)
                log.debug("matched process %s with %s expr", svc,
                          expr_type)
                return svc

    def get_services_expanded(self, name):
        _expanded = []
        for line in CLIHelper().systemctl_list_units():
            expr = r'^\s*({}(@\S*)?)\.service'.format(name)
            ret = re.compile(expr).match(line)
            if ret:
                _expanded.append(ret.group(1))

        if not _expanded:
            _expanded = [name]

        return _expanded

    @cached_property
    def _service_filtered_ps(self):
        """
        For each service get list of processes started by that service and
        get their corresponding binary name from ps.

        Returns list of lines from ps that match the service pids.
        """
        ps_filtered = []
        path = os.path.join(HotSOSConfig.DATA_ROOT,
                            'sys/fs/cgroup/unified/system.slice')
        for svc in self.services:
            for svc in self.get_services_expanded(svc):
                _path = os.path.join(path, "{}.service".format(svc),
                                     'cgroup.procs')
                if not os.path.exists(_path):
                    _path = glob.glob(os.path.join(path, 'system-*.slice',
                                                   "{}.service".format(svc),
                                                   'cgroup.procs'))
                    if not _path or not os.path.exists(_path[0]):
                        continue

                    _path = _path[0]

                with open(_path) as fd:
                    for pid in fd:
                        for line in self._ps:
                            if re.match(r'^\S+\s+{}\s+'.format(int(pid)),
                                        line):
                                ps_filtered.append(line)
                                break

        return ps_filtered

    @cached_property
    def processes(self):
        """
        Identify running processes from ps that are associated with resolved
        systemd services. The same search pattern used for identifying systemd
        services is to match the process binary name.

        Returns a dictionary of process names along with the number of each.
        """
        _proc_info = {}
        for line in self._service_filtered_ps:
            for expr in self._service_exprs:
                """
                look for running process with this name.
                We need to account for different types of process binary e.g.

                /snap/<name>/1830/<svc>
                /usr/bin/<svc>

                and filter e.g.

                /var/lib/<svc> and /var/log/<svc>
                """
                cmd = self.get_process_cmd_from_line(line, expr)
                if cmd:
                    if cmd in _proc_info:
                        _proc_info[cmd] += 1
                    else:
                        _proc_info[cmd] = 1

        return _proc_info

    @property
    def _service_info(self):
        """Return a dictionary of systemd services grouped by state. """
        info = {}
        for svc, obj in sorted_dict(self.services).items():
            state = obj.state
            if state not in info:
                info[state] = []

            info[state].append(svc)

        return info

    @property
    def _process_info(self):
        """Return a list of processes associated with services. """
        return ["{} ({})".format(name, count)
                for name, count in sorted_dict(self.processes).items()]

    @property
    def summary(self):
        """
        Output a dict summary of this class i.e. services, their state and any
        processes run by them.
        """
        return {'systemd': self._service_info,
                'ps': self._process_info}
