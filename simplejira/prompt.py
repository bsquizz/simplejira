from __future__ import print_function

import argparse

import cmd2
import prompter
import yaml

from .common import editor_ignore_comments, sanitize_worklog_time, PkgResource
from .resource_collections import issue_collection, worklog_collection
from .wrapper import JiraWrapper, InvalidLabelError


def _selector(list_to_select_from, title):
    if len(list_to_select_from) == 0:
        return prompter.prompt(title, default="")

    enumerated = list(enumerate(sorted(list_to_select_from)))

    print(title + "\n")
    for entry in enumerated:
        print("  {} / {}".format(entry[0], entry[1]))

    def get_valid_input():
        input = prompter.prompt("enter selection", default="")

        if input.isdigit():
            input = int(input)
            if input < len(enumerated):
                return enumerated[input][1]
            else:
                print("Invalid number")
                return None
        else:
            return input

    print("Enter name, number, type in your own, or leave blank: ")
    input = None
    while not input:
        input = get_valid_input()
    return input


class Prompt(cmd2.Cmd):
    def _init_jira(self):
        """
        Instantiates JiraWrapper and initializes it (loads properties)
        """
        self._jw = JiraWrapper(config_file=self.config_file)
        self._jw.init()
        self._jira = self._jw.jira

    def __init__(self, config_file):
        self.abbrev = True
        cmd2.Cmd.__init__(self, use_ipython=False)
        self.prompt = "(simplejira) "
        self.allow_cli_args = True
        self.exclude_from_help += [
            'do_load', 'do_py', 'do_pyscript', 'do_shell', 'do_set', 'do_shortcuts', 'do_history',
            'do_edit',
        ]

        self.config_file = config_file
        self.issue_collection = None
        
        self._init_jira()

        print("\nWelcome to simplejira!  We hope you have a BLAST.\n")
        print("Type 'help' or '?' to get started.\n")

    def input(self, *args, **kwargs):
        return prompter.prompt(*args, **kwargs)

    # -----------------
    # reload
    # -----------------
    def do_reload(self, args):
        """re-initialize JIRA connection"""
        self._init_jira()

    # -----------------
    # ls
    # -----------------
    ls_parser = argparse.ArgumentParser()
    ls_parser.add_argument(
        '-u', '--user', type=str, default=None,
        help='Issue assignee. Default is yourself.')
    ls_parser.add_argument(
        '-s', '--sprint', type=str, default=None,
        help='Sprint name, sprint number, or "backlog". Default is current sprint.')
    ls_parser.add_argument(
        '-S', '--status', type=str, default=None,
        help='Status of the card. e.g. "inprogress" or "In Progress"')
    ls_parser.add_argument(
        '-t', '--text', type=str, default=None,
        help='Search by text in title or description of the card e.g. --text "5.8 BZs"')
    @cmd2.with_argparser(ls_parser)
    def do_ls(self, args):
        sprint_id = None
        if args.sprint == "backlog":
            sprint_id = args.sprint
        elif args.sprint:
            _, sprint_id = self._jw.find_sprint(args.sprint)
        status = None
        if args.status:
            status = self._jw.find_status_name(args.status)
        issues = self._jw.search_issues(args.user, sprint_id, status, args.text)
        self.issue_collection = issue_collection(issues)
        self.issue_collection.print_table()

    # -----------------
    # card
    # -----------------
    card_parser = argparse.ArgumentParser()
    card_parser.add_argument('number', type=int, help="Card # from table to operate on")
    card_parser.add_argument('cmd', nargs=argparse.REMAINDER,
                             help="Command to pass on to card prompt (optional)")
    @cmd2.with_argparser(card_parser)
    def do_card(self, args):
        if not self.issue_collection:
            print("No issue table generated yet. Run 'ls' or 'search' first.")
            return
        ce = CardEditor(self._jw, self.issue_collection.select(args.number))
        if args.cmd:
            ce.onecmd(" ".join(args.cmd))
        else:
            ce.cmdloop()

    # -----------------
    # create
    # -----------------
    create_parser = argparse.ArgumentParser()
    create_parser.add_argument('-e', '--editor', default=False, action="store_true",
                               help="Open a text editor to fill out issue parameters")
    create_parser.add_argument('-s', '--summary', type=str, default=None, help='Issue summary')
    create_parser.add_argument('-d', '--details', type=str, default=None, help='Issue details')
    create_parser.add_argument('-c', '--component', type=str, default=None, help='Component')
    create_parser.add_argument('-l', '--label', type=str, default=None, help='Label')
    create_parser.add_argument('-a', '--assignee', type=str, default=None,
                               help='Assignee\'s user ID. Default=yourself')
    create_parser.add_argument('-S', '--sprint', type=str, default=None,
                               help='Sprint name, sprint number, or "blacklog". Default=current')
    create_parser.add_argument('-T', '--timeleft', type=str, default=None,
                               help='Estimated time remaining, e.g. "5h30m"')
    @cmd2.with_argparser(create_parser)
    def do_create(self, args):
        curr_sprint_name = self._jw.current_sprint_name
        myid = self._jw.userid

        if args.editor:
            kwargs = yaml.safe_load(
                editor_ignore_comments(PkgResource.read(PkgResource.ISSUE_TEMPLATE))
            )

            # Convert 'label' kwarg to 'labels' for JiraWrapper.create_issue()
            kwargs['labels'] = [kwargs['label']]
            del kwargs['label']
            if not kwargs['sprint']:
                kwargs['sprint'] = curr_sprint_name
            if not kwargs['assignee']:
                kwargs['assignee'] = myid
        else:
            curr_sprint_name = self._jw.current_sprint_name
            print("Enter issue details below. Hit Ctrl+C to cancel and return to prompt.")
            kwargs = {}
            kwargs['summary'] = self.input("Summary/title:")
            kwargs['details'] = self.input("Details:", default="")
            c_l_map = self._jw.component_labels_map
            kwargs['component'] = _selector(
                c_l_map.keys() if len(c_l_map) > 0 else [], "Enter component")
            kwargs['labels'] = [_selector(
                c_l_map[kwargs['component']] if kwargs['component'] in c_l_map else [],
                "Enter label")]
            kwargs['assignee'] = self.input("Assignee:", default=myid)
            kwargs['sprint'] = self.input("Sprint name, id, or 'backlog':",
                                          default=curr_sprint_name)
            kwargs['timeleft'] = self.input("Time left (e.g. 2h30m)", default="")

        try:
            self._jw.create_issue(**kwargs)
        except InvalidLabelError as e:
            print(str(e))
            confirm = prompter.yesno("Use these labels anyway?")
            if not confirm:
                del kwargs['labels']
                print("Removed labels from the issue, please use 'addlabels' later to add proper labels")
            self._jw.create_issue(**kwargs)

    # -----------------
    # edit
    # -----------------
    def do_edit(self, args):
        """edit card details (opens editor)"""
        print(editor_ignore_comments(self.issue_collection.to_yaml()))

    # -----------------
    # todayswork
    # -----------------
    def do_todayswork(self, args):
        """show all work log entries logged today for a generated issue table"""
        if not self.issue_collection:
            print("No issue table generated yet. Run 'ls' or 'search' first")
            return
        worklog_collection(
            self._jw.get_todays_worklogs(self.issue_collection.entries)).print_table()


class CardEditor(cmd2.Cmd):
    def __init__(self, jira_wrapper, issue):
        self.abbrev = True
        self.cmd_shortcuts = {
            'do_1': 'do_ls',
            'do_2': 'do_logwork',
            'do_3': 'do_lswork',
            'do_4': 'do_timeleft',
            'do_5': 'do_component',
            'do_6': 'do_addlabel',
            'do_7': 'do_rmlabels',
            'do_8': 'do_status',
            'do_9': 'do_backlog',
            'do_10': 'do_pull',
            'do_11': 'do_remove',
            'do_12': 'do_assign',
            'do_13': 'do_exit',
        }

        #self.shortcuts.update(self.cmd_shortcuts)
        # ^^ this isn't working ... so let's try this:
        for shortcut, cmd in self.cmd_shortcuts.iteritems():
            setattr(self, shortcut, getattr(self, cmd))

        cmd2.Cmd.__init__(self, use_ipython=False)

        self.prompt = "(card {}) ".format(issue.key)
        self.exclude_from_help += ["do_quit"]

        self._jw = jira_wrapper
        self._jira = self._jw.jira
        self.issue = issue
        self._issue_collection = issue_collection([issue])

    def input(self, *args, **kwargs):
        return prompter.prompt(*args, **kwargs)

    def _print_cmds(self):
        # Print all the commands that can be run against a card
        # We build this list dynamically, based on what shortcuts are defined in self.cmd_shortcuts
        print(
            "\nEditing card {}, select what you want to do (enter number or command):".format(
                self.issue.key)
        )

        for shortcut_num in range(1, len(self.cmd_shortcuts) + 1):
            full_cmd_name = self.cmd_shortcuts["do_" + str(shortcut_num)]

            # Get the description for this cmd
            docstring = getattr(self, full_cmd_name).__doc__
            if "usage" in docstring:
                # This method is using argparse decorator, which adds additional docstring text,
                # so just pull the short description out
                docstring = docstring.split('\n')[2]

            print("  {} / {}\t -- {}".format(shortcut_num, full_cmd_name.lstrip("do_"), docstring))

        print("\nUse 'exit' to get back to main prompt\n")

    def cmdloop(self, *args, **kwargs):
        """
        Print cmds when prompt starts
        """
        self._print_cmds()
        cmd2.Cmd.cmdloop(self, *args, **kwargs)

    def do_exit(self, args):
        """return to main prompt"""
        return self.do_quit(args)

    # -----------------
    # logwork
    # -----------------
    log_parser = argparse.ArgumentParser()
    log_parser.add_argument('timespent', const=None, nargs='?', help="Time spent, e.g. 2h30m")
    log_parser.add_argument('comment', const=None, nargs='*', help="Comment for the work done")
    @cmd2.with_argparser(log_parser)
    def do_logwork(self, args):
        """log work"""
        if not args.timespent:
            args.timespent = self.input("Enter time spent (e.g. 2h30m):")
        if not args.comment:
            args.comment = self.input("Enter comment:")
        else:
            args.comment = " ".join(args.comment)

        self._jira.add_worklog(
            self.issue.key,
            timeSpent=sanitize_worklog_time(args.timespent),
            comment=args.comment
        )

    def _reload_issue(self):
        self.issue = self._jira.issue(self.issue.key)
        return self.issue

    # -----------------
    # ls
    # -----------------
    def do_ls(self, args):
        """re-load this issue from server and show it"""
        self._reload_issue()
        issue_collection([self.issue]).print_table(show_totals=False)

    # -----------------
    # lswork
    # -----------------
    def do_lswork(self, args):
        """show work log"""
        worklogs = self._jw.get_worklog(self.issue)
        worklog_collection(worklogs).print_table()

    # -----------------
    # status
    # -----------------
    status_parser = argparse.ArgumentParser()
    status_parser.add_argument('new_status', const=None, type=str, nargs='*',
                               help="Name of new status (e.g. in progress or inprogress)")
    @cmd2.with_argparser(status_parser)
    def do_status(self, args):
        """change status"""
        avail_statuses = self._jw.get_avail_statuses(self.issue)

        args.new_status = " ".join(args.new_status)

        new_id = self._jw.get_avail_status_id(avail_statuses, args.new_status)
        if not new_id:
            if args.new_status:
                print('"{}" is an invalid status for this issue.'.format(args.new_status))

            print("Available statuses:\n\n")
            for status in avail_statuses:
                print("  {}) {}".format(status['local_num'], status['friendly_name']))
            while True:
                new_id = self._jw.get_avail_status_id(
                    avail_statuses,
                    self.input("Select new status (enter number from above):")
                )
                if new_id:
                    break

        self._jira.transition_issue(self.issue, new_id)

    # -----------------
    # component
    # -----------------
    component_parser = argparse.ArgumentParser()
    component_parser.add_argument('component_name', const=None, type=str, nargs='?')
    @cmd2.with_argparser(component_parser)
    def do_component(self, args):
        """set component"""
        if not args.component_name:
            args.component_name = _selector(self._jw.component_labels_map.keys(), "Enter component")

        self._jw.update_component(self.issue, args.component_name)

    # -----------------
    # addlabels
    # -----------------
    label_parser = argparse.ArgumentParser()
    label_parser.add_argument('label_names', const=None, type=str, nargs='*')
    @cmd2.with_argparser(label_parser)
    def do_addlabel(self, args):
        """add label(s)"""
        if not args.label_names:
            c_l_map = self._jw.component_labels_map
            issue_component = self._jw.get_component(self.issue).lower()
            if issue_component:
                args.label_names = _selector(
                    c_l_map[issue_component] if issue_component in c_l_map else [],
                    "Select label").split(' ')
            else:
                args.label_names = self.input("Enter label(s):").split(' ')
        try:
            self._jw.update_labels(self.issue, args.label_names)
        except InvalidLabelError as e:
            print(str(e))
            confirm = prompter.yesno("Add these labels anyway?")
            if confirm:
                try:
                    self._jw.update_labels(self.issue, args.label_names)
                except InvalidLabelError:
                    pass


    # -----------------
    # rmlabels
    # -----------------
    @cmd2.with_argparser(label_parser)
    def do_rmlabels(self, args):
        """remove label(s)"""
        if not args.label_names:
            args.label_names = self.input("Enter label names (separated by space):").split(' ')
        new_labels = [l for l in self.issue.fields.labels if l not in args.label_names]
        self._jw.update_labels(self.issue, new_labels)

    # -----------------
    # remove
    # -----------------
    def do_remove(self, args):
        """remove this issue"""
        self.issue.delete()
        print("Deleted card, returning to main prompt...")
        self.do_quit()

    # -----------------
    # backlog
    # -----------------
    def do_backlog(self, args):
        """move this issue to the backlog"""
        self._jira.move_to_backlog([self.issue.key])

    # -----------------
    # timeleft
    # -----------------
    """adjust estimated time left"""
    timeleft_parser = argparse.ArgumentParser()
    timeleft_parser.add_argument('time_string', const=None, type=str, nargs='*',
                                 help="Estimated time remaining (e.g. 2h30m)")
    @cmd2.with_argparser(timeleft_parser)
    def do_timeleft(self, args):
        if not args.time_string:
            args.time_string = self.input("Enter time left (e.g. 2h30m)")
        else:
            args.time_string = " ".join(args.time_string)
        self._reload_issue()  # Reload the issue to get timetracking fields
        self._jw.edit_remaining_time(self.issue, args.time_string)

    # -----------------
    # pull
    # -----------------
    def do_pull(self, args):
        """pull this card into your active sprint"""
        self._jira.add_issues_to_sprint(self._jw.current_sprint_id, [self.issue.key])

    '''
    TODO
    def do_edit(self, args):
        """edit issue (opens editor)"""
        #TODO
        #Open an editor for an existing issue, edit the YAML, update the issue
        self._issue_collection.updater(
            self.issue, yaml.safe_load(
                editor_ignore_comments(
                    self._issue_collection.to_yaml(
                        self.issue)))[0])

    def do_editwork(self, args):
        """edit full work log (opens editor)"""
        #TODO
        Open an editor for the worklog entries, edit the YAML, update the worklog
        worklogs = self._jw.get_worklog(self.issue)
        collection = worklog_collection(worklogs)
        print(editor_ignore_comments(collection.to_yaml()))
    '''
    assignee_parser = argparse.ArgumentParser()
    assignee_parser.add_argument('assignee', default=None, type=str, nargs='?',
                                 help="Assign card to someone as assign <username>;"
                                 "username is case insensitive")
    @cmd2.with_argparser(assignee_parser)
    def do_assign(self, args):
        if not args.assignee:
            args.assignee = self.input("Enter assignee user id: [blank to unassign]")
        continue_assignment = False
        if not args.assignee:
            continue_assignment = prompter.yesno(
                    "Leaving assignee blank would unassign the card. Continue?")
        if continue_assignment or args.assignee:
            self._jira.assign_issue(self.issue, args.assignee)
        else:
            print("Assignment did not change.")
