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
from tempfile import TemporaryFile  # Temporary storage for the CLDR source archive.
from zipfile import ZipFile  # No-extraction direct access of archive contents.
from xmltodict import parse  # XML dataset parsing/loading.



def get_target_path(name):
	return pkg_resources.resource_filename('cldr', os.path.join('data', name + '.sqlite3'))


def get_latest_version_url(start=29, template="http://unicode.org/Public/cldr/{}/core.zip"):
	"""Discover the most recent version of the CLDR dataset.
	
	Effort has been made to make this function reusable for other URL numeric URL schemes, just override `start` and
	`template` to iteratively search for the latest version of any other URL.
	"""
	
	latest = None
	
	with Session() as http:  # We perform several requests iteratively, so let's be nice and re-use the connection.
		for current in count(start):
			result = http.head(template.format(current))  # We only care if it exists or not, thus HEAD use here.
			
			if result.status_code != 200:
				return current - 1, latest  # Propagate the version found and the URL for that version.
			
			latest = result.url


@contextmanager
def latest_dataset():
	"""Retrive the latest CLDR dataset and provide a ZipFile interface, handling cleanup automatically.
	
	This streams the dataset into a temporary file before wrapping it in the ZipFile interface.
	"""
	spool = TemporaryFile(prefix='cldr', suffix='.zip')
	version, latest = get_latest_version_url()
	
	with Session() as http:
		response = http.get(latest, stream=True)
		
		for chunk in response.iter_content(chunk_size=4096):
			if chunk: spool.write(chunk)
	
	# Write out any uncommitted data, then return to the beginning.
	spool.flush()
	spool.seek(0)
	
	zipfile = ZipFile(spool, 'r')
	zipfile.version = version  # Expose the version number through to consumers of the ZipFile.
	
	yield zipfile
	
	zipfile.close()
	spool.close()


@contextmanager
def _database(name):
	"""Open the target SQLite dataset by simple, short name, and manage the connection."""
	
	path = get_target_path(name)
	connection = sqlite3.connect(path)
	
	yield connection
	
	connection.commit()
	connection.close()


@contextmanager
def _cursor(connection):
	"""Acquire a new cursor for the given connection and automatically commit upon completion."""
	
	cursor = connection.cursor()
	yield cursor
	connection.commit()


def _recreate(cursor, name, *fields):
	try:
		cursor.execute("DROP TABLE {}".format(name))
	except sqlite3.OperationalError:
		pass
	
	cursor.execute("CREATE TABLE {} ({})".format(name, " text, ".join(fields) + ' text'))


def _extract_values(data, aliased, *names):
	for i in data:
		record = [i[name] for name in names]
		
		if aliased:
			record.append(None)
		
		yield record
		
		if aliased and '@alias' in i:
			record = [i['@alias' if name == '@name' else name] for name in names]
			record.append(i['@name'])
			
			yield record


def _simple_store(name, cursor, data, aliased, *names):
	if aliased:
		field_names = list(names) + ['alias']
	else:
		field_names = names
	
	_recreate(cursor, name, *field_names)
	values = _extract_values(data, aliased, *[('@' + field) for field in names])
	sql = "INSERT INTO {} VALUES ({})".format(name, ('?, ' * len(field_names))[:-2])
	cursor.executemany(sql, values)


class Dataset(object):
	def __call__(self, archive):
		extractors = [i for i in dir(self) if i.startswith('extract_')]
		
		with _database(self.NAME) as db:
			for name in extractors:
				extractor = getattr(self, name)
				filename = "common/{}/{}.xml".format(getattr(self, 'PREFIX', self.NAME), name[8:])
				data = archive.open(filename, 'rU')
				
				with _cursor(db) as cursor:
					extractor(parse(data.read(), 'utf-8'), cursor)
				
				data.close()


class BCP47Dataset(Dataset):
	NAME = 'bcp47'
	
	def extract_calendar(self, content, cursor):
		"""This dataset contains: calendar algorithm, first day of week, and hour cycle."""
		
		parts = {i['@name']: i for i in content['ldmlBCP47']['keyword']['key']}
		
		def store_ca(data):
			_simple_store('calendar_ca', cursor, data, True, 'name', 'description')
		
		def store_fw(data):
			_simple_store('calendar_fw', cursor, data, False, 'name', 'description')
		
		def store_hc(data):
			_simple_store('calendar_hc', cursor, data, False, 'name', 'description')
		
		__import__('pudb').set_trace()
		
		for key in parts:
			locals()['store_' + key](parts[key]['type'])





def update_cldr_dataset():
	fh = ZipFile('core.zip', 'r')
	
	ds = BCP47Dataset()
	ds(fh)
	
	fh.close()



if __name__ == "__main__":
	update_cldr_dataset()

