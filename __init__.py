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
from .routes import judge0_bp

log = logging.getLogger("ctfd.plugins.judge0")


def load(app):
    upgrade(plugin_name="judge0")
    # Tables come from migrations/. create_all() is only the sqlite fallback
    # inside upgrade(); calling it again here would fight MariaDB.

    CHALLENGE_CLASSES["judge0"] = Judge0CodeChallenge
    register_plugin_assets_directory(app, base_path="/plugins/judge0/assets/")
    app.register_blueprint(judge0_bp)
    register_admin_plugin_menu_bar(title="Judge0", route="/plugins/judge0/admin/settings")
    log.info("[JUDGE0] plugin loaded")
