"""
Contains utils such as update checker

"""
from distutils.version import StrictVersion

import pkg_resources
import requests


PYPI_URL = "https://pypi.python.org/pypi/jiraprompt/json"


def _compare_version(pypi_version):
    pypi_version = StrictVersion(pypi_version)
    try:
        local_version = pkg_resources.get_distribution("jiraprompt").version
    except pkg_resources.DistributionNotFound:
        local_version = "0.0.0"

    try:
        my_version = StrictVersion(local_version)
    except ValueError:
        print(f"Version '{local_version}' seems to be a dev version, assuming up-to-date")
        my_version = StrictVersion("999.999.999")

    if my_version < pypi_version:
        print(
            " "
            "There is a new version available! (yours: {}, available: {})"
            " "
            "Upgrade with:"
            "    pip install --upgrade jiraprompt"
            " ".format(my_version, pypi_version)
        )
    else:
        print("Up-to-date!")


def check_pypi():
    print("\nChecking pypi for latest release...")

    pkg_data = {}
    try:
        response = requests.get(PYPI_URL, timeout=5)
        response.raise_for_status()
        pkg_data = response.json()
    except requests.exceptions.Timeout:
        print("Unable to reach pypi quickly, giving up.")
    except requests.exceptions.HTTPError as e:
        print("Error response from pypi: ", e.errno, e.message)
    except ValueError:
        print("Response was not valid json, giving up.")

    try:
        pypi_version = pkg_data["info"]["version"]
    except KeyError:
        print("Unable to parse version info from pypi")
    else:
        _compare_version(pypi_version)
    print("\n")
