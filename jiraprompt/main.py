import argparse
import os
import sys
from pathlib import Path

import prompter
import yaml

from .common import editor_preserve_comments
from .prompt import MainPrompt
from .res import get_ascii_art
from .res import get_default_config
from .res import get_default_labels
from .utils.update_check import check_pypi


DEFAULT_CONFIG_FILE = "config.yaml"
DEFAULT_LABELS_FILE = "labels.yaml"


def _get_config_path():
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        config_home = Path(xdg_config_home)
    else:
        config_home = Path.home().joinpath(".config")

    return config_home.joinpath("jiraprompt")


def _write_config_file(filename, txt):
    path = _get_config_path().joinpath(filename)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(txt.encode("utf8").decode("utf8"))
    path.chmod(0o600)
    return path


def _create_config_files():
    new_config = editor_preserve_comments(get_default_config())
    config_path = _write_config_file(DEFAULT_CONFIG_FILE, new_config)

    new_labels_config = editor_preserve_comments(get_default_labels())
    labels_path = _write_config_file(DEFAULT_LABELS_FILE, new_labels_config)

    print(f"Writing config to {config_path}")
    print(f"Writing labels config to {labels_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-file", type=str)
    parser.add_argument("--labels-file", type=str)
    args, unknown_args = parser.parse_known_args()

    if args.config_file:
        config_path = Path(args.config_file)
    else:
        config_path = _get_config_path().joinpath(DEFAULT_CONFIG_FILE)
        if not config_path.exists():
            print("It looks like you have no config created.\n")
            if prompter.yesno("Create one now?"):
                _create_config_files()

    if not config_path.exists():
        print("ERROR: No valid config file found.")
        sys.exit(1)

    if args.labels_file:
        labels_path = Path(args.labels_file)
    else:
        labels_path = _get_config_path().joinpath(DEFAULT_LABELS_FILE)
    if not labels_path.exists():
        print(f"WARNING: Labels config file not found at '{labels_path}'")
        labels_path = ""

    # print welcome msg
    print(get_ascii_art().decode("utf8"))

    # check for updates if enabled
    with config_path.open() as f:
        cfg = yaml.safe_load(f)
    if cfg.get("check_for_updates", True):
        check_pypi()

    sys.argv = sys.argv[:1] + unknown_args

    main_prompt = MainPrompt(config_file=str(config_path), labels_file=str(labels_path))
    main_prompt.cmdloop()


if __name__ == "__main__":
    main()
