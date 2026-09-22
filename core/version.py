# core/version.py
"""
Single source of truth for the tiny build-version badge shown at the
bottom of the sidebar (see templates/core/base.html). Its whole purpose
is to make it obvious at a glance, on the live site itself, whether a
deploy actually picked up the latest code.

Format: MAJOR.MINOR.PATCH, patch zero-padded to 2 digits (1.0.01,
1.0.02, ... 1.0.10, ...). Bump PATCH by one with every commit meant to
reach production; MAJOR/MINOR are bumped manually for real milestones,
not by this per-commit convention.
"""
APP_VERSION = "1.0.02"
