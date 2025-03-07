import abc
import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper, HostNetworkingHelper
from hotsos.core.searchtools import FileSearcher

KERNLOG_TS = r'\[\s*\d+\.\d+\]'
KERNLOG_PREFIX = (r'(?:\S+\s+\d+\s+[\d:]+\s+\S+\s+\S+:\s+)?{}'.
                  format(KERNLOG_TS))


class CallTraceHeuristicBase(object):
    """ Defines a common interface for heuristics implementations. """

    @abc.abstractmethod
    def __call__(self):
        """ Ensure callable to get results. """


class CallTraceStateBase(object):
    """
    A state capture object that allows getting and setting arbitrary state.
    """

    def __init__(self):
        self._info = {}

    def add(self, key, value):
        self._info[key] = value

    def __getattr__(self, key):
        return self._info.get(key)


class TraceTypeBase(abc.ABC):
    """
    This defines a common interface to trace types and should be implemented
    for any trace types we want to capture. Implementations of this object
    are typically registered with a CallTraceManager for processing.
    """

    @abc.abstractproperty
    def name(self):
        """
        Name used to identify the type of call trace e.g. "oomkiller".
        """

    @abc.abstractproperty
    def searchdef(self):
        """
        A search definition object (simple or sequence) used to identify this
        call trace.
        """

    @abc.abstractmethod
    def apply(self, results):
        """
        Take results and parse into constituent parts.

        @param results: a SearchResultsCollection object containing the results
        of our search.
        """

    @abc.abstractproperty
    def heuristics(self):
        """ Return a list of CallTraceHeuristic objects that can be used to
        run checks on any identified call traces. """

    @abc.abstractmethod
    def __len__(self):
        """ Return number of call stacks identified.  """

    @abc.abstractmethod
    def __iter__(self):
        """ Iterate over each call trace found. """


class KernLogBase(object):

    def __init__(self):
        self.searcher = FileSearcher()
        self.hostnet_helper = HostNetworkingHelper()
        self.cli_helper = CLIHelper()

    @property
    def path(self):
        path = os.path.join(HotSOSConfig.DATA_ROOT, 'var/log/kern.log')
        if HotSOSConfig.USE_ALL_LOGS:
            return "{}*".format(path)

        return path
