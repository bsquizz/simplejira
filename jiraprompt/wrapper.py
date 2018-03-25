from __future__ import print_function

import getpass
import warnings

import attr
import yaml
from jira import JIRA
from jira.exceptions import JIRAError

from .common import (
    iso_time_is_today, sanitize_worklog_time, friendly_worklog_time, iso_time_is_yesterday)


class InvalidLabelError(Exception):
    def __init__(self, component, label, *args, **kwargs):
        super(InvalidLabelError, self).__init__(*args, **kwargs)
        self.component = component
        self.label = label

    def __str__(self):
        return "Label '{}' is not valid for component '{}'".format(self.label, self.component)


class JiraClientOverride(JIRA):
    def _create_kerberos_session(self, *args, **kwargs):
        """
        Little hack to get auth cookies from JIRA when using kerberos, otherwise
        queries to other URLs hit a 401 and are not handled properly for some
        reason

        https://stackoverflow.com/questions/21578699/jira-rest-api-and-kerberos-authentication
        """
        super(JiraClientOverride, self)._create_kerberos_session(*args, **kwargs)
        print("Attempting to authenticate with kerberos...")
        r = self._session.get("{}/step-auth-gss".format(self._options['server']))
        if r.status_code == 200:
            print("Authenticated successfully")


class IssueFields(object):
    """
    Class which holds builders for various jira field data

    Build multiple field sections and then pass in the entire kwarg without having to remember the
    json variations.
    Example:

    f = IssueFields().labels(['something1', 'something2']).component("LOL").summary("my summary")
    issue.update(**f.kwarg)
    """
    def __init__(self):
        self._base = {'fields': {}}
        self.fields = self._base['fields']

    @property
    def kwarg(self):
        return self._base

    def timetracking(self, remaining, original):
        self.fields.update({
            'timetracking': {
                'remainingEstimate': sanitize_worklog_time(str(remaining)),
                'originalEstimate': sanitize_worklog_time(str(original))
            }
        })
        return self

    def component(self, component_name):
        if component_name:
            self.fields.update({
                'components': [
                    {'name': component_name}
                ]
            })
        return self

    def labels(self, label_list):
        if label_list:
            self.fields.update({
                'labels': label_list
            })
        return self

    def summary(self, summary_text):
        if summary_text:
            self.fields.update({
                'summary': summary_text
            })
        return self

    def description(self, description_text):
        if description_text:
            self.fields.update({
                'description': description_text
            })
        return self

    def assignee(self, name):
        if name:
            self.fields.update({
                'assignee': {
                    'name': name
                }
            })
        return self

    def issuetype(self, name):
        if name:
            self.fields.update({
                'issuetype': {
                    'name': name
                }
            })
        return self

    def project(self, name=None, key=None, id=None):
        kwargs = {'name': name, 'key': key, 'id': id}
        if not any(kwargs.values()):
            raise ValueError("project needs at least 1 of: [name, key, id] defined")

        d = {'project': {}}    

        for key, value in kwargs.items():
            if value:
                d['project'][key] = value

        self.fields.update(d)
        return self

@attr.s
class JiraWrapper(object):
    """
    Provides utils for storing config and interacting with python-jira
    """
    config_file = attr.ib()
    labels_file = attr.ib()

    _config = attr.ib(default=attr.Factory(dict))
    _component_labels_map = attr.ib(default=attr.Factory(dict))
    _jira = attr.ib(default=None)
    _current_sprint_id = attr.ib(default=0)
    _current_sprint_name = attr.ib(type=str, default=None)
    _board_id = attr.ib(default=0)
    _project_id = attr.ib(default=0)
    _userid = attr.ib(type=str, default=None)

    def __attrs_post_init__(self):
        """
        After object instantiation, load config files
        """
        with open(self.config_file, 'r') as f:
            self._config = yaml.safe_load(f)
        if self.labels_file:
            with open(self.labels_file, 'r') as f:
                self._component_labels_map = yaml.safe_load(f)

    @property
    def jira_url(self):
        """
        Server URL being used for JIRA.
        """
        return self._config['url']

    @property
    def label_check(self):
        try:
            return self._config['label_check']
        except KeyError:
            return False

    @property
    def verify_ssl(self):
        try:
            return self._config['verify_ssl']
        except KeyError:
            return True

    @property
    def jira(self):
        """
        Creates the JiraClient session
        """
        if not self._jira:
            print("Connecting to jira at", self.jira_url)
            kwargs = {}
            cfg = self._config
            auth_cfg = cfg['auth']
            kwargs['validate'] = False

            if 'basic_auth' in auth_cfg and auth_cfg['basic_auth'] is True:
                print("Using basic authentication")
                if 'password' in auth_cfg and auth_cfg['password']:
                    password = auth_cfg['password']
                else:
                    password = getpass.getpass("Enter your JIRA password: ")
                kwargs['basic_auth'] = (auth_cfg['username'], password)
            else:
                print("Using kerberos authentication")
                kwargs['kerberos'] = True
                kwargs['kerberos_options'] = {'mutual_authentication': "DISABLED"}

            kwargs['options'] = {'server': self.jira_url}
            if 'ca_cert_path' in self._config:
                kwargs['options']['verify'] = self._config['ca_cert_path']
            if self.verify_ssl is False:
                print("Warning: SSL certificate verification is disabled!")
                kwargs['options']['verify'] = False
                # Disable ssl validation warnings, we gave one warning already ...
                from urllib3.exceptions import InsecureRequestWarning
                from requests.packages.urllib3 import disable_warnings
                disable_warnings(category=InsecureRequestWarning)

            self._jira = JiraClientOverride(**kwargs)
        return self._jira

    @property
    def board_id(self):
        if not self._board_id:
            try:
                cfgboard = str(self._config['board']).lower()
            except KeyError:
                raise KeyError("config has no 'board' defined!")

            boards = self.jira.boards()

            for b in boards:
                if b.name.lower() == cfgboard or str(b.id) == cfgboard:
                    self._board_id = str(b.id)
                    break

            if not self._board_id:
                raise ValueError("Unable to find board '{}'".format(self._config['board']))
        return self._board_id

    @property
    def project_id(self):
        if not self._project_id:
            try:
                cfgproject = str(self._config['project']).lower()
            except KeyError:
                raise KeyError("config has no 'project' defined!")

            projects = self.jira.projects()

            for p in projects:
                if any(x == cfgproject for x in [p.key.lower(), p.name.lower(), str(p.id)]):
                    self._project_id = str(p.id)
                    break

            if not self._project_id:
                raise ValueError("Unable to find project '{}'".format(self._config['project']))
        return self._project_id

    @property
    def userid(self):
        if not self._userid:
            self._userid = self.jira.myself()['key']

        return self._userid

    def find_sprint(self, txt):
        """
        Return sprint ID whose name or ID contains "txt", case insensitive.

        Args:
          txt: string or int

        Returns:
          tuple of (sprint_name, sprint_id)
        """
        sprints = self.jira.sprints(board_id=self.board_id)
        for s in sprints:
            txt = str(txt).lower()
            if txt.isdigit() and txt in [n for n in s.name.split() if n.isdigit()]:
                return s.name, str(s.id)
            elif not txt.isdigit() and txt in s.name.lower():
                return s.name, str(s.id)
        raise ValueError("Unable to find sprint with text: ", str(txt))

    def get_current_sprint(self):
        active_sprints = (
            sprint for sprint
            in self.jira.sprints(board_id=self.board_id, state='active')
            if sprint.state.lower() == 'active'
        )
        current_sprint = sorted(active_sprints, key=lambda sprint: sprint.id)[-1]
        self._current_sprint_id = str(current_sprint.id)
        self._current_sprint_name = current_sprint.name
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
                "(Sprint = EMPTY OR Sprint not in (openSprints(), futureSprints()))"
                .format(self.project_id))
        else:
            sprint = self.current_sprint_id if not sprint else sprint
            search_query = 'sprint = {} '.format(sprint)
        if not assignee:
            assignee = "currentUser()"
        search_query += ' AND assignee = {}'.format(assignee)
        if status:
            search_query += ' AND status in ("{}")'.format(status)
        if text:
            search_query += ' AND (summary ~ "{}" OR description ~ "{}")'.format(text, text)
        return self.jira.search_issues(search_query)

    def get_my_issues(self):
        return self.search_issues()

    def get_worklog(self, issue):
        return self.jira.worklogs(issue.key)

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
        issues = self.jira.search_issues(
            'sprint = {} AND assignee = currentUser() AND '
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
        return txt.replace(' ', '').lower()

    @property
    def component_labels_map(self):
        try:
            lowercase_data = {
                k.lower(): [l.lower() for l in v]
                for k, v in self._component_labels_map.items()
            }
        except KeyError:
            lowercase_data = {}
        return lowercase_data

    def find_component(self, txt):
        """
        Find component whose name or id matches 'txt', case insensitive

        Args:
          txt: str or int

        Returns:
          tuple of (component_name, component_id)
        """
        components = self.jira.project_components(self.project_id)
        for c in components:
            if (str(txt).isdigit and str(c.id) == str(txt)) or str(txt).lower() in c.name.lower():
                return c.name, c.id
        raise ValueError("Unable to find component with text: ", str(txt))

    def _check_comp_labels(self, component, labels):
        if not component or not labels:
            return
        if self.label_check:
            comp_lower = component.lower()
            labels_lower = [l.lower() for l in labels]
            if comp_lower in self.component_labels_map:
                for l in labels_lower:
                    if l not in self.component_labels_map[comp_lower]:
                        raise InvalidLabelError(component, l)

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

        if hasattr(issue, 'components') and len(issue.components) > 0:
            self._check_comp_labels(issue.components[0].name, labels)

        issue.update(**f.kwarg)

    def find_status_name(self, txt):
        """
        Find the server-side status name based on 'txt' input.

        Will search using 'normalized' strings -- e.g. whitepsace removed and lowercase

        This way if txt is 'inprogress' this matches to "In Progress"
        """
        txt = self.normalize_name(txt)
        statuses = self._jira.statuses()
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
                'name': JiraWrapper.normalize_name(t['name']),  # used for name matching
                'id': t['id'],
                'friendly_name': t['name'],
            } for t in self.jira.transitions(issue) if 'Parallel Team' not in t['name']
        ]
        avail_statuses.sort(key=lambda s: s['name'])
        for idx, status in enumerate(avail_statuses):
            status['local_num'] = idx + 1
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
            if normalized_name == s['name'] or (txt.isdigit() and int(txt) == s['local_num']):
                return s['id']
        return None

    def create_issue(self, summary, details=None, component=None,
                     labels=None, assignee=None, sprint=None, timeleft=None,
                     issuetype='Task', force_labels=False):
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
        else:
            _, sprint_id = self.find_sprint(sprint)

        if not force_labels:
            self._check_comp_labels(component, labels)

        f = IssueFields()
        comp_name_server_side, _ = self.find_component(component)
        f.summary(summary) \
            .description(details) \
            .component(comp_name_server_side) \
            .labels(labels) \
            .project(id=self.project_id) \
            .issuetype(issuetype) \
            .timetracking(timeleft, timeleft)
        
        new_issue = self.jira.create_issue(**f.kwarg)
        
        if assignee:
            self.jira.assign_issue(new_issue.key, assignee)

        if sprint == "backlog":
            self.jira.move_to_backlog([new_issue.key])
        else:
            self.jira.add_issues_to_sprint(sprint_id, [new_issue.key])

    def init(self):
        """Initialize all properties in one shot so it doesn't have to be done later."""
        # Note that these init self.jira too...
        print("Connecting to JIRA & gathering some info ...")
        try:
            self.userid
        except JIRAError as e:
            if 'CAPTCHA_CHALLENGE' in e.text:
                print("Your userID currently requires answering a CAPTCHA to login via basic auth")
                raw_input("Open {} in a browser, log in there to answer the CAPTCHA\n"
                           "Hit 'enter' here when done.".format(self.jira_url))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Hide jira greenhopper API warnings
            print("UserID:", self.userid)
            print("Project ID:", self.project_id)
            print("Board ID:", self.board_id)
            print("Current sprint name:", self.current_sprint_name)
            print("Current sprint ID:", self.current_sprint_id)
