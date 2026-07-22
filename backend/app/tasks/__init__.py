"""Celery task modules.

Each submodule registers its tasks via @celery_app.task. They're
imported by celery_app.py's `include=[...]` so the worker discovers
them at startup.
"""
