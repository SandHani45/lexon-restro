# core/version.py
"""
Single source of truth for the tiny build-version badge shown at the
bottom of the sidebar (see templates/core/base.html). Its whole purpose
is to make it obvious at a glance, on the live site itself, whether a
deploy actually picked up the latest code -- bump APP_VERSION by one
with every commit meant to reach production.
"""
APP_VERSION = "B2"
