import os
from django.core.management.base import BaseCommand, CommandError

checkout_script = """#!/bin/bash
REPO_URL="https://github.com/arodic/polygone.art.git"
DEST_DIR="polygone_data"

mkdir $DEST_DIR && cd $DEST_DIR
git init
git config core.sparseCheckout true
echo "assets/*/*.json" >> .git/info/sparse-checkout
git remote add origin $REPO_URL
git pull origin main
"""

class Command(BaseCommand):
    help = "Sparse checkout of polygone json data"
    def handle(self, *args, **options):
        os.system(checkout_script)



