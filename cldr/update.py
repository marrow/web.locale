# encoding: utf-8

"""Download the latest Unicode CLDR data and update SQlite caches.

To update the installed package, run:

	python -m cldr.update

This library ships with a default set of SQLite databases, but they can be updated at any time independent of package
releases.
"""

from __future__ import unicode_literals

import os.path  # Cross-platform path manipulation.
import pkg_resources  # Cross-platform package-relative path utilities.
import sqlite3  # Local, efficient, queryable data storage.

from marrow.package.loader import traverse  # Simplify lookup of data.
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
	
	fields = ["{} {}".format(*i[:2]) if isinstance(i, tuple) else "{} text".format(i) for i in fields]
	
	cursor.execute("CREATE TABLE {} ({})".format(name, ", ".join(fields)))


def _extract_values(data, aliased, *names):
	for i in data:
		record = [i.get(name[0] if isinstance(name, tuple) else name, None) for name in names]
		
		if aliased:
			record.append(None)
		
		yield record
		
		if aliased and '@alias' in i:
			for alias in i['@alias'].split():
				record = [alias if name == '@name' else i[name] for name in names]
				record.append(i['@name'])
				
				yield record


def _simple_store(name, cursor, data, aliased, *names):
	if aliased:
		field_names = [i[0] if isinstance(i, tuple) else i for i in names] + ['alias']
	else:
		field_names = names
	
	_recreate(cursor, name, *field_names)
	values = _extract_values(data, aliased, *[('@' + field[0], field[1]) if isinstance(field, tuple) else ('@' + field) for field in names])
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



def to_date(value):
	if not value: return value
	from datetime import date
	return date(*[int(i) for i in value.split('-')])


def to_bool(value):
	if value in [True, 1, "yes", "true"]:
		return True
	
	if value in [False, 0, "no", "false"]:
		return False
	
	return bool(value)


class CurrencySupplementalDataset(Dataset):
	NAME = 'currency'
	PREFIX = 'supplemental'
	
	def extract_supplementalData(self, content, cursor):
		rounding = traverse(content, 'supplementalData.currencyData.fractions.info')
		
		_simple_store('rounding', cursor, rounding, False,
				'iso4217',
				('digits', 'int'),
				('rounding', 'int'),
				('cashDigits', 'int'),
				('cashRounding', 'int'))
		
		# This gets a bit more complex, as we need to store typecast, date-ranged data.
		_recreate(cursor, 'region', 'region', 'currency', 'start', 'end', ('tender', 'bool'))
		
		values = []
		for region in traverse(content, 'supplementalData.currencyData.region'):
			for currency in (region['currency'] if isinstance(region['currency'], list) else [region['currency']]):
				values.append((
						region['@iso3166'],
						currency['@iso4217'],
						to_date(currency.get('@from', None)),
						to_date(currency.get('@to', None)),
						to_bool(currency.get('@tender', True)),
					))
		
		cursor.executemany("INSERT INTO region VALUES (?, ?, ?, ?, ?)", values)




class TerritorySupplementalDataset(Dataset):
	NAME = 'territory'
	PREFIX = 'supplemental'
	
	def extract_supplementalData(self, content, cursor):
		# Prepare the data source and destination.
		containment = traverse(content, 'supplementalData.territoryContainment.group')
		languages = traverse(content, 'supplementalData.languageData.language')
		
		_recreate(cursor, 'containment', 'parent', 'child', 'intermediary')
		_recreate(cursor, 'containment_path', 'territory', 'path')
		_recreate(cursor, 'language', 'territory', 'language', 'script', ('secondary', 'bool'))
		
		# The containment of territories within eachother and within logical groupings, from UN data.
		
		values = []
		mapping = {}
		
		for group in containment:
			if group.get('@status', None) == 'deprecated': continue
			members = group['@contains'].split()
			intermediary = (group.get('status', None) == 'grouping') or all(i.isnumeric() for i in members)
			for member in members:
				mapping[member] = group['@type']
				values.append((
						group['@type'],
						member,
						intermediary
					))
		
		cursor.executemany("INSERT INTO containment VALUES (?, ?, ?)", values)
		
		# A reverse mapping of these, to quickly look up a "breadcrumb" for display or navigation.
		
		values = []
		
		for key in mapping:
			if key.isnumeric() or key == 'EU': continue
			parent = mapping[key]
			path = []
			
			while parent:
				path.append(parent)
				parent = mapping.get(parent, None)
				if parent == '001': break
			
			values.append((key, ' '.join(path)))
		
		cursor.executemany("INSERT INTO containment_path VALUES (?, ?)", values)
		
		# languages typically associated with certain territories.
		
		values = []
		
		for language in languages:
			if '@territories' not in language: continue
			
			for territory in language['@territories'].split():
				for script in language['@scripts'].split() if '@scripts' in language else [None]:
					values.append((
							territory,
							language['@type'],
							script,
							language.get('@alt', None) == 'secondary'
						))
		
		cursor.executemany("INSERT INTO language VALUES (?, ?, ?, ?)", values)
	
	def extract_telephoneCodeData(self, content, cursor):
		content = traverse(content, 'supplementalData.telephoneCodeData.codesByTerritory')
		
		_recreate(cursor, 'telephone_code', 'territory', 'code')
		
		values = []
		for item in content:
			codes = item['telephoneCountryCode']
			
			if not isinstance(codes, list):
				codes = [codes]
			
			for code in codes:
				values.append((item['@territory'], code['@code']))
		
		cursor.executemany("INSERT INTO telephone_code VALUES (?, ?)", values)



class BCP47Dataset(Dataset):
	NAME = 'bcp47'
	
	def extract_calendar(self, content, cursor):
		"""This dataset contains: calendar algorithm, first day of week, and hour cycle."""
		
		parts = {i['@name']: i for i in content['ldmlBCP47']['keyword']['key'] if not i.get('@deprecated', None)}
		for key in parts:
			_simple_store('calendar_' + key, cursor, parts[key]['type'], True, 'name', 'description')
	
	def extract_collation(self, content, cursor):
		"""This dataset contains a large number of individal property sets."""
		
		parts = {i['@name']: i for i in content['ldmlBCP47']['keyword']['key'] if not i.get('@deprecated', None)}
		for key in parts:
			if key == 'kr': continue
			_simple_store('collation_' + key, cursor, parts[key]['type'], True, 'name', 'description')
	
	def extract_currency(self, content, cursor):
		parts = {i['@name']: i for i in content['ldmlBCP47']['keyword']['key'] if not i.get('@deprecated', None)}
		for key in parts:
			_simple_store('currency_' + key, cursor, parts[key]['type'], True, 'name', 'description')
	
	def extract_measure(self, content, cursor):
		_simple_store('measure', cursor, content['ldmlBCP47']['keyword']['key']['type'], True, 'name', 'description')
	
	def extract_number(self, content, cursor):
		_simple_store('number', cursor, content['ldmlBCP47']['keyword']['key']['type'], True, 'name', 'description')
	
	def extract_timezone(self, content, cursor):
		_simple_store('timezone', cursor, content['ldmlBCP47']['keyword']['key']['type'], False, 'name', 'description', 'preferred', 'alias')
	
	def extract_variant(self, content, cursor):
		_simple_store('variant_em', cursor, content['ldmlBCP47']['keyword']['key'][0]['type'], False, 'name', 'description', 'preferred', 'alias')


def update_cldr_dataset():
	fh = ZipFile('core.zip', 'r')
	
	ds = BCP47Dataset()
	ds(fh)
	
	ds = CurrencySupplementalDataset()
	ds(fh)
	
	ds = TerritorySupplementalDataset()
	ds(fh)
	
	fh.close()



if __name__ == "__main__":
	update_cldr_dataset()

