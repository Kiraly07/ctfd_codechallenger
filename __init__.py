"""Judge0 Code Challenge type for CTFd.

Target: CTFd 3.8.x (verified against 3.8.6). The challenge type is registered
on CHALLENGE_CLASSES and the extra tables are created by the plugin migration
runner, which dynamic_challenges uses as well.
"""

from __future__ import annotations

import logging

from CTFd.plugins import register_admin_plugin_menu_bar, register_plugin_assets_directory
from CTFd.plugins.challenges import CHALLENGE_CLASSES
from CTFd.plugins.migrations import upgrade

from .challenge import Judge0CodeChallenge
from .routes import ctfd_code_bp

log = logging.getLogger("ctfd.plugins.ctfd_code")


def load(app):
    upgrade(plugin_name="ctfd_code")
    # Tables come from migrations/. create_all() is only the sqlite fallback
    # inside upgrade(); calling it again here would fight MariaDB.

    CHALLENGE_CLASSES["ctfd_code"] = Judge0CodeChallenge
    register_plugin_assets_directory(app, base_path="/plugins/ctfd_code/assets/")
    app.register_blueprint(ctfd_code_bp)
    register_admin_plugin_menu_bar(title="Code", route="/plugins/ctfd_code/admin/settings")
    log.info("[CTFD_CODE] plugin loaded")
