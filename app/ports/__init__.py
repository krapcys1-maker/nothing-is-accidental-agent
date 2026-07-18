"""Porty (kontrakty) oddzielające logikę od infrastruktury.

Sześć portów z archiwalnego IMPLEMENTATION_PLAN.md §B.6 (docs/archive/superseded_plans/):
SchedulerPort, StoragePort, BrowserPort, SecretStorePort, FileStorePort, NotificationPort.

W walking skeleton realnie używane są: StoragePort (SQLite), SecretStorePort (.env),
FileStorePort (lokalny FS), NotificationPort (log). SchedulerPort i BrowserPort są
stubami — Playwright i harmonogram włączymy w kolejnych etapach.
"""
