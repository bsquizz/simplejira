"""
handles access to common ressources

"""
import pkg_resources
from functools import partial

ASCII_ART = 'resources/ascii_art.txt'
DEFAULT_CONFIG = 'resources/config_default.yml'
ISSUE_TEMPLATE = 'resources/issue_template.yml'

get_default_config = partial(pkg_resources.resource_string,
                             __name__, DEFAULT_CONFIG)
get_ascii_art = partial(pkg_resources.resource_string,
                        __name__, ASCII_ART)
get_issue_template = partial(pkg_resources.resource_string,
                             __name__, ISSUE_TEMPLATE)
