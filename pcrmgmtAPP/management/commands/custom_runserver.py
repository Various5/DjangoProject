# pcrmgmtAPP/management/commands/custom_runserver.py

from django.core.management.commands.runserver import Command as RunserverCommand
from django.db.utils import OperationalError
from django.shortcuts import render

class Command(RunserverCommand):
    def check_migrations(self):
        try:
            super().check_migrations()
        except OperationalError:
            self.stdout.write(self.style.WARNING("Database not available. Skipping migration check."))
