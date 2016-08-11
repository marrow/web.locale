# encoding: utf-8

"""Download the latest Unicode CLDR data and update SQlite caches.

To update the installed package, run:

	python -m cldr.update

This library ships with a default set of SQLite databases, but they can be updated at any time independent of package
releases.
"""

import os.path  # Cross-platform path manipulation.
import pkg_resources  # Cross-platform package-relative path utilities.
import sqlite3  # Local, efficient, queryable data storage.

from itertools import count  # Atomic counter used when determining latest version.
from contextlib import contextmanager  # Shortens some of our code later.
from requests import Session  # HTTP download management.
from zipfile import ZipFile  # No-extraction direct access of archive contents.



def get_target_path(name):
	return pkg_resources.resource_filename('cldr', os.path.join('data', name + '.sqlite3'))


def get_latest_version_url(start=29, template="http://unicode.org/Public/cldr/{}/core.zip"):
	"""Discover the most recent version of the CLDR dataset."""
	
	latest = None
	
	with Session() as http:
		for current in count(start):
			result = http.head(template.format(current))
			
			if result.status_code != 200:
				return latest
			
			latest = result.url



def update_cldr_dataset():
	print(get_latest_version_url())


if __name__ == "__main__":
	update_cldr_dataset()

