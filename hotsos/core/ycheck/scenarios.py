from hotsos.core.config import HotSOSConfig
from hotsos.core.issues import IssuesManager, HotSOSScenariosWarning
from hotsos.core.log import log
from hotsos.core.ycheck.engine import (
    YDefsLoader,
    YDefsSection,
    YHandlerBase,
)


class Scenario(object):
    def __init__(self, name, checks, conclusions):
        log.debug("scenario: %s", name)
        self.name = name
        self._checks = checks
        self._conclusions = conclusions

    @property
    def checks(self):
        return {c.name: c for c in self._checks}

    @property
    def conclusions(self):
        return {c.name: c for c in self._conclusions}


class YScenarioChecker(YHandlerBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scenarios = []

    def load(self):
        plugin_content = YDefsLoader('scenarios').plugin_defs
        if not plugin_content:
            return

        yscenarios = YDefsSection(HotSOSConfig.PLUGIN_NAME, plugin_content)
        if (not HotSOSConfig.FORCE_MODE and yscenarios.requires and not
                yscenarios.requires.passes):
            log.debug("plugin '%s' scenarios pre-requisites not met - "
                      "skipping", HotSOSConfig.PLUGIN_NAME)
            return

        log.debug("sections=%s, scenarios=%s",
                  len(yscenarios.branch_sections),
                  len(yscenarios.leaf_sections))

        to_skip = set()
        for scenario in yscenarios.leaf_sections:
            # Only register scenarios if requirements are satisfied.
            group_name = scenario.parent.name
            if (group_name in to_skip or
                    (scenario.requires and not scenario.requires.passes)):
                log.debug("%s requirements not met - skipping scenario %s",
                          group_name, scenario.name)
                to_skip.add(group_name)
                continue

            scenario.checks.initialise(scenario.vars, scenario.input)
            scenario.conclusions.initialise(scenario.vars)
            self._scenarios.append(Scenario(scenario.name,
                                            scenario.checks,
                                            scenario.conclusions))

    @property
    def scenarios(self):
        return self._scenarios

    def _run_scenario_conclusion(self, scenario, issue_mgr):
        """ Determine the conclusion of this scenario. """
        results = {}
        # run all conclusions and use highest priority result(s). One or
        # more conclusions may share the same priority. All conclusions
        # that match and share the same priority will be used.
        for name, conc in scenario.conclusions.items():
            if conc.reached(scenario.checks):
                if conc.priority:
                    priority = conc.priority.value
                else:
                    priority = 1

                if priority in results:
                    results[priority].append(conc)
                else:
                    results[priority] = [conc]

                log.debug("conclusion reached: %s (priority=%s)", name,
                          priority)

        if results:
            highest = max(results.keys())
            log.debug("selecting highest priority=%s conclusions (%s)",
                      highest, len(results[highest]))
            for conc in results[highest]:
                issue_mgr.add(conc.issue, context=conc.issue_context)
        else:
            log.debug("no conclusions reached")

    def run(self):
        failed_scenarios = []
        issue_mgr = IssuesManager()
        for scenario in self.scenarios:
            log.debug("running scenario: %s", scenario.name)
            # catch failed scenarios and allow others to run
            try:
                self._run_scenario_conclusion(scenario, issue_mgr)
            except Exception:
                log.exception("caught exception when running scenario %s:",
                              scenario.name)
                failed_scenarios.append(scenario.name)

        if failed_scenarios:
            msg = ("One or more scenarios failed to run ({}) - run hotsos in "
                   "debug mode (--debug) to get more detail".
                   format(', '.join(failed_scenarios)))
            issue_mgr.add(HotSOSScenariosWarning(msg))
