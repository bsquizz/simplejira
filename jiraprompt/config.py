import os
from pathlib import Path

import attr
import yaml
from cached_property import cached_property

from .common import editor_preserve_comments
from .res import get_default_config


DEFAULT_CONFIG_FILE = "config.yaml"


@attr.s
class Config:
    config_path = attr.ib(type=str, default=None)

    @cached_property
    def path(self):
        if self.config_path:
            return Path(self.config_path)

        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config_home:
            config_home = Path(xdg_config_home)
        else:
            config_home = Path.home().joinpath(".config")

        return config_home.joinpath("jiraprompt").joinpath(DEFAULT_CONFIG_FILE)

    def create_config_file(self):
        new_config = editor_preserve_comments(get_default_config())

        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.write_text(new_config.encode("utf8").decode("utf8"))
        self.path.chmod(0o600)

        print(f"Saved config to {self.path}")

    def load(self):
        default_config = yaml.safe_load(get_default_config())
        with self.path.open() as f:
            config = yaml.safe_load(f)
        for key in default_config:
            if key in config:
                self.__dict__[key] = config[key]
            else:
                self.__dict__[key] = default_config[key]
        for key in config:
            if key not in default_config:
                print(f"WARNING: Ignoring unknown config key '{key}'")
