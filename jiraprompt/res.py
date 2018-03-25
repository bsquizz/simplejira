"""
handles access to common resources
"""
from functools import partial
import pkg_resources

ASCII_ART = 'resources/ascii_art.txt'
DEFAULT_CONFIG = 'resources/config_default.yml'
DEFAULT_LABELS = 'resources/labels_default.yml'
ISSUE_TEMPLATE = 'resources/issue_template.yml'

get_default_config = partial(pkg_resources.resource_string,
                             __name__, DEFAULT_CONFIG)
get_default_labels = partial(pkg_resources.resource_string,
                             __name__, DEFAULT_LABELS)
get_ascii_art = partial(pkg_resources.resource_string,
                        __name__, ASCII_ART)
get_issue_template = partial(pkg_resources.resource_string,
                             __name__, ISSUE_TEMPLATE)
