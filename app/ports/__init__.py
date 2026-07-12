"""Porty (kontrakty) oddzielające logikę od infrastruktury.

Sześć portów z IMPLEMENTATION_PLAN.md §B.6:
SchedulerPort, StoragePort, BrowserPort, SecretStorePort, FileStorePort, NotificationPort.

W walking skeleton realnie używane są: StoragePort (SQLite), SecretStorePort (.env),
FileStorePort (lokalny FS), NotificationPort (log). SchedulerPort i BrowserPort są
stubami — Playwright i harmonogram włączymy w kolejnych etapach.
"""
