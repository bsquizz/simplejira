import re
from datetime import datetime
from datetime import timedelta

import editor
import iso8601
from dateutil import parser
from dateutil import tz


def editor_preserve_comments(default_text):
    """
    Open pyeditor and preserves comments. Does some encoding stuff.
    """
    if not isinstance(default_text, bytes):
        default_text = default_text.encode("utf-8")
    edited_text = editor.edit(contents=default_text)
    if not isinstance(edited_text, str):
        edited_text = edited_text.decode("utf-8")
    return edited_text


def editor_ignore_comments(default_text):
    """
    Open pyeditor but ignore lines starting with "#" when text is returned.

    :param default_text:
    :return:
    """
    if not isinstance(default_text, bytes):
        default_text = default_text.encode("utf-8")
    edited_text = editor.edit(contents=default_text)
    if not isinstance(edited_text, str):
        edited_text = edited_text.decode("utf-8")
    lines = edited_text.split("\n")
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


def sanitize_worklog_time(s):
    """
    Convert a time string entered by user
    to jira-acceptable format for issue time tracking
    """
    s = s.replace(" ", "")

    def get_number_before(letter):
        number = 0
        try:
            regex_str = fr"\D*(\d*)\s*{letter}.*"
            number = re.findall(regex_str, s)[0]
        except (AttributeError, IndexError):
            pass
        return number

    days = get_number_before("d")
    hours = get_number_before("h")
    mins = get_number_before("m")
    secs = get_number_before("s")

    new_s = ""
    new_s += days + "d " if days else ""
    new_s += hours + "h " if hours else ""
    new_s += mins + "m " if mins else ""
    new_s += secs + "s " if secs else ""
    if new_s:
        return new_s
    else:
        # user might not have specified any strings at all,
        # just pass along the int
        return s


def friendly_worklog_time(seconds):
    """
    https://stackoverflow.com/questions/775049/how-to-convert-seconds-to-hours-minutes-and-seconds

    :param seconds:
    :return:
    """
    if not seconds:
        string = "0m"
    else:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        string = ""
        string += f"{h}h" if h else ""
        string += f"{m}m" if m else ""
        string += f"{s}s" if s else ""
    return string


def iso_to_datetime(string):
    tz_utc = tz.tzutc()
    tz_local = tz.tzlocal()
    utc_datetime = iso8601.parse_date(string)
    utc_datetime = utc_datetime.replace(tzinfo=tz_utc)
    return utc_datetime.astimezone(tz_local)


# Using a time format that explicitly specifies %Z since in some
# environments the time zone was not being printed even
# if the datetime object had 'tzinfo'
TIME_FORMAT = "%a %x %X %Z"


def iso_to_ctime_str(string):
    datetime_object = iso_to_datetime(string)
    return datetime_object.strftime(TIME_FORMAT)


def ctime_str_to_datetime(datetime_string):
    return parser.parse(datetime_string)


def ctime_str_to_iso(datetime_string):
    return ctime_str_to_datetime(datetime_string).isoformat()


def iso_time_is_today(string):
    datetime_object = iso_to_datetime(string)
    return datetime.today().date() == datetime_object.date()


def iso_time_is_yesterday(string):
    datetime_object = iso_to_datetime(string)
    return (datetime.today().date() - timedelta(1)) == datetime_object.date()
