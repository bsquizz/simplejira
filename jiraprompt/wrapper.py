import warnings

import attr
from cached_property import cached_property

from .client import JiraClient
from .common import friendly_worklog_time
from .common import iso_time_is_today
from .common import iso_time_is_yesterday
from .common import sanitize_worklog_time


class IssueFields:
    """
    Class which holds builders for various jira field data

    Build multiple field sections and then pass in the entire kwarg without having to remember the
    json variations.
    Example:

    f = IssueFields().labels(['something1', 'something2']).component("LOL").summary("my summary")
    issue.update(**f.kwarg)
    """

    def __init__(self):
        self._base = {"fields": {}}
        self.fields = self._base["fields"]

    @property
    def kwarg(self):
        return self._base

    def timetracking(self, remaining, original):
        self.fields.update(
            {
                "timetracking": {
                    "remainingEstimate": sanitize_worklog_time(str(remaining)),
                    "originalEstimate": sanitize_worklog_time(str(original)),
                }
            }
        )
        return self

    def component(self, component_name):
        if component_name:
            self.fields.update({"components": [{"name": component_name}]})
        return self

    def labels(self, label_list):
        if label_list:
            self.fields.update({"labels": label_list})
        return self

    def summary(self, summary_text):
        if summary_text:
            self.fields.update({"summary": summary_text})
        return self

    def description(self, description_text):
        if description_text:
            self.fields.update({"description": description_text})
        return self

    def assignee(self, name):
        if name:
            self.fields.update({"assignee": {"name": name}})
        return self

    def issuetype(self, name):
        if name:
            self.fields.update({"issuetype": {"name": name}})
        return self

    def project(self, name=None, key=None, id=None):
        kwargs = {"name": name, "key": key, "id": id}
        if not any(kwargs.values()):
            raise ValueError("project needs at least 1 of: [name, key, id] defined")

        d = {"project": {}}

        for key, value in kwargs.items():
            if value:
                d["project"][key] = value

        self.fields.update(d)
        return self


@attr.s
class JiraWrapper:
    """
    Provides utils for storing config and interacting with python-jira
    """

    config = attr.ib()
    client = attr.ib(type=JiraClient)

    current_sprint_id = attr.ib(default=0)
    current_sprint_name = attr.ib(type=str, default=None)
    board_id = attr.ib(default=0)
    project_id = attr.ib(default=0)

    def find_sprint(self, txt):
        """
        Return sprint ID whose name or ID contains "txt", case insensitive.

        Args:
          txt: string or int

        Returns:
          tuple of (sprint_name, sprint_id)
        """
        sprints = self.client.sprints(board_id=self.board_id)
        for s in sprints:
            txt = str(txt).lower()
            if txt.isdigit() and txt in [n for n in s.name.split() if n.isdigit()]:
                return s.name, str(s.id)
            elif not txt.isdigit() and txt in s.name.lower():
                return s.name, str(s.id)
        raise ValueError("Unable to find sprint with text: ", str(txt))

    def get_current_sprint(self, board_id):
        active_sprints = (
            sprint
            for sprint in self.client.sprints(board_id=board_id, state="active")
            if sprint.state.lower() == "active"
        )
        current_sprint = sorted(active_sprints, key=lambda sprint: sprint.id)[-1]
        return current_sprint

    @property
    def current_sprint_id(self):
        """
        Returns currently active sprint ID for the agile board.
        """
        if not self._current_sprint_id:
            self.get_current_sprint()
        return self._current_sprint_id

    @property
    def current_sprint_name(self):
        if not self._current_sprint_name:
            self.get_current_sprint()
        return self._current_sprint_name

    @cached_property
    def info_for_board(self):
        if not self.config.boards:
            raise ValueError("No boards found in config")

        config_boards = [str(board).lower() for board in self.config.boards]
        server_boards = self.client.boards()
        _info_for_board = {}

        for idx, cb in enumerate(config_boards):
            for sb in server_boards:
                if sb.name.lower() == cb or str(sb.id) == cb:
                    current_sprint = self.get_current_sprint(sb.id)
                    _info_for_board[self.config.boards[idx]] = {
                        "name": sb.name,
                        "id": sb.id,
                        "filter_query": sb.raw.get("filter", {}).get("query"),
                        "current_sprint_name": current_sprint.name,
                        "current_sprint_id": current_sprint.id,
                    }
                    break
            else:
                raise ValueError(f"Unable to find board '{cb}' on server")

        return _info_for_board

    @cached_property
    def info_for_project(self):
        if not self.config.projects:
            raise ValueError("No projects found in config")

        config_projects = [str(project).lower() for project in self.config.projects]
        server_projects = self.client.projects()
        _info_for_project = {}

        for idx, cp in enumerate(config_projects):
            for sp in server_projects:
                if any(x == cp for x in [sp.key.lower(), sp.name.lower(), str(sp.id)]):
                    _info_for_project[self.config.projects[idx]] = {
                        "id": sp.id,
                        "key": sp.key,
                        "name": sp.name,
                    }
                    break
            else:
                raise ValueError(f"Unable to find project '{cp}' on server")

        return _info_for_project

    def search_issues(self, assignee=None, sprint=None, status=None, text=None):
        """
        Search issues

        Args:
           sprint: sprint ID number, sprint name, or "backlog", default is current sprint
           assignee: user id, default is "currentUser"
           status: for e.x. "in progress"

        Returns:
            List of JIRA.Issue resources
        """
        if sprint == "backlog":
            search_query = (
                "project = {} AND issuetype != Epic AND resolution = Unresolved AND "
                "status != Done AND "
                "(Sprint = EMPTY OR Sprint not in (openSprints(), futureSprints()))".format(
                    self.project_id
                )
            )
        else:
            sprint = self.current_sprint_id if not sprint else sprint
            search_query = f"sprint = {sprint} "
        if not assignee:
            # Make sure we are still logged in, otherwise an empty list may be returned.
            self.client.myself()
            assignee = "currentUser()"
        search_query += f" AND assignee = {assignee}"
        if status:
            search_query += f' AND status in ("{status}")'
        if text:
            search_query += f' AND (summary ~ "{text}" OR description ~ "{text}")'
        return self.client.search_issues(search_query)

    def get_my_issues(self):
        return self.search_issues()

    def get_worklog(self, issue):
        # Make sure we are still logged in, otherwise an empty list may be returned.
        self.client.myself()
        return self.client.worklogs(issue.key)

    def get_todays_worklogs(self, issue_list):
        worklogs = []

        for issue in issue_list:
            for wl in self.get_worklog(issue):
                if iso_time_is_today(wl.started):
                    worklogs.append(wl)
        return worklogs

    def get_yesterdays_worklogs(self, issue_list):
        worklogs = []

        for issue in issue_list:
            for wl in self.get_worklog(issue):
                if iso_time_is_yesterday(wl.started):
                    worklogs.append(wl)
        return worklogs

    @staticmethod
    def edit_remaining_time(issue, time_string):
        """
        Set remaining time estimate on an issue.

        Keep originalEstimate and only edit remainingEstimate
        We need to pass both of them as not passing originalEstimate zeroes it.
        """
        try:
            original = issue.fields.timetracking.originalEstimate
        except AttributeError:
            print("Warning: issue had no timetracking field, using timeoriginalestimate field")
            original = friendly_worklog_time(issue.fields.timeoriginalestimate)
        f = IssueFields().timetracking(time_string, original)
        issue.update(**f.kwarg)

    @staticmethod
    def zero_remaining_time(issue):
        JiraWrapper.edit_remaining_time(issue, 0)

    def zero_remaining_work_done(self):
        """
        Find all "Done" issues assigned to me in the current sprint and 0 their time estimate.
        """
        issues = self.client.search_issues(
            "sprint = {} AND assignee = currentUser() AND "
            'status = "Done" AND remainingEstimate > 0'.format(self.current_sprint_id)
        )

        for issue in issues:
            self.zero_remaining_time(issue)

    @staticmethod
    def normalize_name(txt):
        """
        Strip whitespace and switch to lowercase

        For example: "In Progress" becomes "inprogress"
        """
        return txt.replace(" ", "").lower()

    def find_component(self, txt):
        """
        Find component whose name or id matches 'txt', case insensitive

        Args:
          txt: str or int

        Returns:
          tuple of (component_name, component_id)
        """
        components = self.client.project_components(self.project_id)
        # First, try exact match
        for c in components:
            if (str(txt).isdigit and str(c.id) == str(txt)) or str(txt).lower() == c.name.lower():
                return c.name, c.id
        # Second, if we are still here, try fuzzy match
        for c in components:
            if str(txt).lower() in c.name.lower():
                return c.name, c.id
        raise ValueError("Unable to find component with text: ", str(txt))

    def update_component(self, issue, component_name):
        server_side_name, _ = self.find_component(component_name)
        f = IssueFields().component(server_side_name)
        issue.update(**f.kwarg)

    @staticmethod
    def get_component(issue):
        if len(issue.fields.components) > 0:
            return issue.fields.components[0].name
        else:
            return None

    def update_labels(self, issue, labels):
        f = IssueFields().labels(labels)

        if hasattr(issue, "components") and len(issue.components) > 0:
            self._check_comp_labels(issue.components[0].name, labels)

        issue.update(**f.kwarg)

    def find_status_name(self, txt):
        """
        Find the server-side status name based on 'txt' input.

        Will search using 'normalized' strings -- e.g. whitepsace removed and lowercase

        This way if txt is 'inprogress' this matches to "In Progress"
        """
        txt = self.normalize_name(txt)
        statuses = self.client.statuses()
        for s in statuses:
            if txt == self.normalize_name(s.name):
                return s.name
        return None

    def get_avail_statuses(self, issue):
        """
        Find available status transitions for the given issue

        Builds a list of dicts, each dict contains:
           name: normalized name of the status, e.g. "inprogress"
           id: server-side if of the status
           friendly_name: the display name, e.g. "In Progress"
           local_num: the idx of this status, used for local selection in the CLI prompts
        """
        avail_statuses = [
            {
                "name": JiraWrapper.normalize_name(t["name"]),  # used for name matching
                "id": t["id"],
                "friendly_name": t["name"],
            }
            for t in self.client.transitions(issue)
            if "Parallel Team" not in t["name"]
        ]
        avail_statuses.sort(key=lambda s: s["name"])
        for idx, status in enumerate(avail_statuses):
            status["local_num"] = idx + 1
        return avail_statuses

    @staticmethod
    def get_avail_status_id(avail_statuses, txt):
        """
        Given a string name for an issue status, find the server-side id that correlates with it.

        Args:
            avail_statuses: list of avail status info return by JiraWrapper.get_avail_statuses()
            txt: string for status, e.x. "in progress" or "inprogress"
                 can also be a number which matches the status 'local_num' in avail_statuses

        Returns:
            status ID or None
        """
        for s in avail_statuses:
            normalized_name = JiraWrapper.normalize_name(txt)
            if normalized_name == s["name"] or (txt.isdigit() and int(txt) == s["local_num"]):
                return s["id"]
        return None

    def create_issue(
        self,
        summary,
        details=None,
        component=None,
        labels=None,
        assignee=None,
        sprint=None,
        timeleft=None,
        issuetype="Task",
        force_labels=False,
    ):
        """
        Create an issue (by default, a Story) in the agile sprint.

        Args:
          summary (str): issue title/summary
          details (str): detailed issue description
          component (str): component name
          labels (list of str): labels
          assignee (str): user id of assignee
          sprint (str): sprint name, sprint number, or 'backlog'. Default is current sprint
          timeleft (str): estimated time remaining (e.g. 2h30m)
          issueype (str): issue type, default is "Story", you likely won't change this.
          force_labels (boolean): don't check if labels/components are valid

        Returns:
          The newly created JIRA.Issue resource
        """

        if labels and not isinstance(labels, list):
            raise TypeError("labels must be a list")

        if not sprint:
            sprint_id = self.current_sprint_id
        elif sprint != "backlog":
            _, sprint_id = self.find_sprint(sprint)

        if not force_labels:
            self._check_comp_labels(component, labels)

        f = IssueFields()
        comp_name_server_side, _ = self.find_component(component)
        f.summary(summary).description(details).component(comp_name_server_side).labels(
            labels
        ).project(id=self.project_id).issuetype(issuetype).timetracking(timeleft, timeleft)

        new_issue = self.client.create_issue(**f.kwarg)

        if assignee:
            self.client.assign_issue(new_issue.key, assignee)

        if sprint == "backlog":
            self.client.move_to_backlog([new_issue.key])
        else:
            self.client.add_issues_to_sprint(sprint_id, [new_issue.key])

    def init(self):
        """Initialize all properties in one shot so it doesn't have to be done later."""
        # Note that these init self.client too...
        from pprint import pprint

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Hide jira greenhopper API warnings
            pprint(self.info_for_board)
            pprint(self.info_for_project)
