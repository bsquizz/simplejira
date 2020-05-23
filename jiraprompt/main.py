import argparse
import sys

import prompter

from .config import Config
from .prompt import MainPrompt
from .res import get_ascii_art
from .utils.update_check import check_pypi


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-file", type=str)
    args, unknown_args = parser.parse_known_args()

    config = Config(args.config_file)
    if not config.path.exists():
        print(f"No config found at '{config.path}'.\n")
        if prompter.yesno("Create one now?"):
            config.create_config_file()

    if not config.path.exists():
        print("ERROR: No valid config file found.")
        sys.exit(1)

    config.load()

    # print welcome msg
    print(get_ascii_art().decode("utf8"))

    # check for updates if enabled
    if config.check_for_updates:
        check_pypi()

    sys.argv = sys.argv[:1] + unknown_args

    main_prompt = MainPrompt(config=config)
    main_prompt.cmdloop()


if __name__ == "__main__":
    main()
