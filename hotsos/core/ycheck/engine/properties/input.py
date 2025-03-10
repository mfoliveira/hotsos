import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.log import log
from hotsos.core.utils import mktemp_dump
from hotsos.core.ycheck.engine.properties.common import (
    cached_yproperty_attr,
    YPropertyOverrideBase,
    add_to_property_catalog,
)


class YPropertyInputBase(object):

    @property
    def options(self):
        defaults = {'disable-all-logs': False,
                    'args': [],
                    'kwargs': {},
                    'args-callback': None}

        if type(self.content) == dict:
            _options = self.content.get('options', defaults)
            defaults.update(_options)

        return defaults

    @property
    def command(self):
        return self.content.get('command')

    def expand_paths(self, paths):
        _paths = []
        for path in paths:
            path = os.path.join(HotSOSConfig.DATA_ROOT, path)
            if (HotSOSConfig.USE_ALL_LOGS and not
                    self.options['disable-all-logs']):
                path = "{}*".format(path)

            _paths.append(path)

        return _paths

    @property
    def path(self):
        raise Exception("do not call this directly")

    @cached_yproperty_attr
    def paths(self):
        _paths = []
        fs_path = None
        if type(self.content) in [str, list]:
            fs_path = self.content
        else:
            fs_path = self.content.get('path')

        if fs_path:
            if type(fs_path) == list:
                for path in fs_path:
                    _paths.append(path)
            else:
                _paths.append(fs_path)

            return self.expand_paths(_paths)

        if self.command:
            cmd_tmp_path = self.cache.cmd_tmp_path
            if cmd_tmp_path:
                return [cmd_tmp_path]

            args_callback = self.options['args-callback']
            if args_callback:
                args, kwargs = self.get_method(args_callback)
            else:
                args = self.options['args']
                kwargs = self.options['kwargs']

            # get command output
            out = getattr(CLIHelper(), self.command)(*args, **kwargs)
            # store in temp file to make it searchable
            # NOTE: we dont need to delete this at the the end since they are
            # created in the plugin tmp dir which is wiped at the end of the
            # plugin run.
            if type(out) == list:
                out = ''.join(out)
            elif type(out) == dict:
                out = str(out)

            cmd_tmp_path = mktemp_dump(out)
            self.cache.set('cmd_tmp_path', cmd_tmp_path)
            return [cmd_tmp_path]

        log.debug("no input provided")


@add_to_property_catalog
class YPropertyInput(YPropertyOverrideBase, YPropertyInputBase):

    @classmethod
    def _override_keys(cls):
        return ['input']
