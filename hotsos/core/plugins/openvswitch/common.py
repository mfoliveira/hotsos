from hotsos.core import plugintools
from hotsos.core.host_helpers import APTPackageHelper, SystemdHelper
from hotsos.core.ycheck.events import YEventCheckerBase
from hotsos.core.utils import cached_property, sorted_dict
from hotsos.core.plugins.openvswitch.ovs import OpenvSwitchBase


OVS_SERVICES_EXPRS = [r'ovsdb[a-zA-Z-]*',
                      r'ovs-vswitch[a-zA-Z-]*',
                      r'ovn[a-zA-Z-]*',
                      'openvswitch-switch',
                      ]
OVS_PKGS_CORE = ['openvswitch-switch',
                 'ovn',
                 ]
OVS_PKGS_DEPS = ['libc-bin',
                 'openvswitch',
                 'ovsdbapp',
                 'openssl',
                 'openvswitch-switch-dpdk',
                 ]
PY_CLIENT_PREFIX = r"python3?-{}\S*"


class OpenvSwitchChecksBase(OpenvSwitchBase, plugintools.PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        p_core = OVS_PKGS_CORE + [PY_CLIENT_PREFIX.format(p)
                                  for p in OVS_PKGS_CORE]
        p_deps = OVS_PKGS_DEPS + [PY_CLIENT_PREFIX.format(p)
                                  for p in OVS_PKGS_DEPS]
        self.apt = APTPackageHelper(core_pkgs=p_core, other_pkgs=p_deps)
        self.systemd = SystemdHelper(service_exprs=OVS_SERVICES_EXPRS)

    @cached_property
    def apt_packages_all(self):
        return self.apt.all

    @property
    def plugin_runnable(self):
        # require at least one core package to be installed to run this plugin.
        return len(self.apt.core) > 0


class OpenvSwitchEventChecksBase(OpenvSwitchChecksBase, YEventCheckerBase):

    @property
    def summary(self):
        # mainline all results into summary root
        ret = self.run_checks()
        if ret:
            return sorted_dict(ret)
