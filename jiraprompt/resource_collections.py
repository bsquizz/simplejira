from __future__ import print_function

import copy
from inspect import isclass, isfunction

import attr
import yaml
from attr.validators import optional, instance_of
from jira.resources import Resource, Issue, Worklog
from prettytable import PrettyTable

from .common import iso_to_ctime_str, friendly_worklog_time, iso_to_datetime
from six import string_types


@attr.s
class ResourceCollection(object):
    """
    Represents an ordered set of Jira Resource entries (issues, worklogs, etc.)

    Contains methods that dictate the entries from a field
    that should be displayed/operated on,
    how they should be sorted, updated, printed, etc.

    This class uses attrs to instantiate objects,
    and collections that hold different Resource
    types are instantiated by methods below this class.
    """

    """ defines type of resource in this collection """
    entry_type = attr.ib()

    @entry_type.validator
    def is_entry_type(self, attribute, value):
        if not (isclass(value) and issubclass(value, Resource)):
            raise TypeError("entry_type needs to be a Resource subclass")

    """ defines list of the resource objects """
    entries = attr.ib(type=list)

    @entries.validator
    def valiadate_entries(self, __, value):
        for element in value:
            if not isinstance(element, self.entry_type):
                raise TypeError(element, self.entry_type)

    """ defines the field names that are displayed for each resource """
    field_names = attr.ib(type=list)

    @field_names.validator
    def validate_field_names(self, __, value):
        for v in value:
            if not isinstance(v, string_types):
                raise ValueError(v)

    """ defines the fields that should be 'aligned left' when table is printed """
    align_left = attr.ib(type=list)

    @align_left.validator
    def validate_align_left(self, _, value):
        for element in value:
            if element not in self.field_names:
                raise ValueError(element)

    """ method which takes an entry from this collection and builds a row (list) for the table """
    row_builder = attr.ib()

    @row_builder.validator
    def test_row(self, attribute, value):
        valid = False
        if isfunction(value):
            try:
                if self.entries:
                    value(self.entries[0])
                    valid = True
            except Exception:
                print("ERROR: provided row_builder failed to build a row from entry 0")
                raise
        return valid

    """ method which takes row data as input and updates the resource server-side """
    """ Not sure if we'll be using this yet... """
    updater = attr.ib()

    """ optional, method which takes all entries and totals certain fields """
    totals_row_builder = attr.ib(default=None)

    @totals_row_builder.validator
    def test_totaler(self, attribute, value):
        valid = False
        if isfunction(value):
            try:
                totals_row = value(self.entries)
                if len(totals_row) != len(self.field_names):
                    raise TypeError("ERROR: totals row does not match len of other rows")
            except Exception:
                print("ERROR: provided totals_row_builder failed validation")
                raise
            valid = True
        return valid

    """ method which becomes the key for sorting this collection's list of resources """
    sorter = attr.ib(
        default=None,
        validator=optional(lambda _, __, value: isfunction(value)))

    # these should usually not be passed in by the caller and are populated by @properties below
    _table = attr.ib(default=None,
                     validator=optional(instance_of(PrettyTable)))
    _table_with_totals = attr.ib(default=None,
                                 validator=optional(instance_of(PrettyTable)))

    @property
    def table(self):
        """
        Generate a pretty table for the collection

        Uses the row_builder method to create a row and add it to the PrettyTable
        Also adds an additional column at the front, the "No." column which lists the entry number
        """
        if not self._table:
            t = PrettyTable()
            t.field_names = ["no."] + self.field_names
            for idx, entry in enumerate(self.entries):
                new_row = self.row_builder(entry)
                new_row = [idx + 1] + new_row
                t.add_row(new_row)
            for field in self.align_left:
                t.align[field] = "l"

            self._table = t
        return self._table

    @property
    def table_with_totals(self):
        """
        Generate a pretty table which has a 'totals' row if a row builder method has been given
        """
        if self.table:
            if self.totals_row_builder:
                self._table_with_totals = copy.deepcopy(self.table)
                totals_row = self.totals_row_builder(self.entries)
                totals_row = ["total"] + totals_row
                self._table_with_totals.add_row(totals_row)
            else:
                self._table_with_totals = self.table
        return self._table_with_totals

    def __attrs_post_init__(self):
        """
        Sort the collection's entries after init
        """
        if self.sorter:
            self.entries.sort(key=self.sorter)

    def print_table(self, show_totals=True):
        """
        Print the table for this collection
        """
        if show_totals:
            # A hacky way to add the totals row w/ a line divider before it
            table_lines = str(self.table_with_totals).splitlines()
            divider = table_lines[-1]
            table_lines.insert(-2, divider)
            print("\n".join(table_lines))
        else:
            print(self.table)

    def to_yaml(self, specific_entry=None):
        """
        Using the field names and row values, convert this collection to YAML
        """
        if specific_entry:
            entry_data_list = [specific_entry]
        else:
            entry_data_list = self.entries

        filtered_data_list = []
        for entry in entry_data_list:
            filtered_data = {
                self.field_names[i]: data
                for i, data in enumerate(self.row_builder(entry))
            }
            filtered_data_list.append(filtered_data)
        return yaml.safe_dump(filtered_data_list, default_flow_style=False)

    def select(self, number):
        """
        Select an entry based on its displayed entry number in the table
        """
        return self.entries[number - 1]


def issue_collection(issue_list):
    def row_builder(issue):
        f = issue.fields
        # Truncate the summary if too long
        summary = f.summary[:49] + "..." if len(f.summary) > 50 else f.summary
        row = [
            issue.key,
            summary,
            f.components[0].name if len(f.components) else "",
            ", ".join(f.labels) if len(f.labels) else "",
            f.status.name,
            friendly_worklog_time(f.timespent),
            friendly_worklog_time(f.timeestimate),
        ]
        return row

    def updater(issue, new_data):
        """
        Not sure if we'll be using this yet ...
        """
        '''
        issue.update(
            key=new_data['key'],
            summary=new_data['summary'],
            fields={
                'components': [{'name': new_data['component']}],
                'labels': [new_data['label']],
                'status': {'name': new_data['status']},
                'timespent': new_data['timeSpent'],
                'timeestimate': new_data['timeEstimate']
            }
        )
        TODO: transition status
        '''

    def totals_row_builder(issue_list):
        total_timespent = friendly_worklog_time(
            sum(issue.fields.timespent or 0 for issue in issue_list)
        )
        total_timeest = friendly_worklog_time(
            sum(issue.fields.timeestimate or 0 for issue in issue_list)
        )
        return ["", "", "", "", "", total_timespent, total_timeest]

    return ResourceCollection(
        entry_type=Issue,
        entries=issue_list,
        field_names=["key", "summary", "component", "label", "status", "timeSpent", "timeLeft"],
        align_left=["summary"],
        row_builder=row_builder,
        updater=updater,
        totals_row_builder=totals_row_builder,
        sorter=lambda issue: issue.fields.status.name
    )


def worklog_collection(worklog_list):
    def row_builder(wl):
        # Truncate comment if too long
        comment = wl.comment[:87] + "..." if len(wl.comment) > 88 else wl.comment
        row = [friendly_worklog_time(wl.timeSpentSeconds), iso_to_ctime_str(wl.started), comment]
        return row

    def totals_row_builder(wl_list):
        total_timespent = friendly_worklog_time(sum(wl.timeSpentSeconds for wl in wl_list))
        return [total_timespent, "", ""]

    return ResourceCollection(
        entry_type=Worklog,
        entries=worklog_list,
        field_names=["timeSpent", "started", "comment"],
        align_left=["comment"],
        row_builder=row_builder,
        updater=None,
        totals_row_builder=totals_row_builder,
        sorter=lambda worklog: iso_to_datetime(worklog.started)
    )
