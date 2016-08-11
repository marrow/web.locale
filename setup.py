#!/usr/bin/env python
# encoding: utf-8

from __future__ import print_function

import os
import sys
import codecs


try:
	from setuptools.core import setup, find_packages
except ImportError:
	from setuptools import setup, find_packages

from setuptools.command.test import test as TestCommand


if sys.version_info < (2, 7):
	raise SystemExit("Python 2.7 or later is required.")
elif sys.version_info > (3, 0) and sys.version_info < (3, 2):
	raise SystemExit("Python 3.2 or later is required.")

exec(open(os.path.join("web", "locale", "release.py")).read())


class PyTest(TestCommand):
	def finalize_options(self):
		TestCommand.finalize_options(self)
		
		self.test_args = []
		self.test_suite = True
	
	def run_tests(self):
		import pytest
		sys.exit(pytest.main(self.test_args))


here = os.path.abspath(os.path.dirname(__file__))

tests_require = [
		'pytest',  # test collector and extensible runner
		'pytest-cov',  # coverage reporting
		'pytest-flakes',  # syntax validation
		'pytest-spec',  # output formatting
	]


setup(
	name = "web.locale",
	version = version,
	
	description = description,
	long_description = codecs.open(os.path.join(here, 'README.rst'), 'r', 'utf8').read(),
	url = url,
	download_url = 'https://github.com/marrow/web.locale/releases',
	
	author = author.name,
	author_email = author.email,
	
	license = 'MIT',
	keywords = [
			'WebCore',  # This package is meant to interoperate with the WebCore framework.
			'web.ext',  # This package provides a WebCore extension.
			'web.command',  # This package provides command-line interface extensions.
			
			# Feature keywords.
			'gilt',  # GILT is the acronym encompassing all of the following individual terms:
			'translation', 't9n',
			'internationalization', 'i18n',
			'localization', 'l10n',
			'regionalization', 'r13n',
			'globalization', 'g11n',
			
			# Abstract terms.
			'language', 'number', 'currency', 'format', 'calendar', 'date', 'money'
		],
	classifiers = [
			"Development Status :: 4 - Beta",
			"Environment :: Console",
			"Environment :: Web Environment",
			"Intended Audience :: Developers",
			"License :: OSI Approved :: MIT License",
			"Operating System :: OS Independent",
			"Programming Language :: Python",
			"Programming Language :: Python :: 2",
			"Programming Language :: Python :: 2.7",
			"Programming Language :: Python :: 3",
			"Programming Language :: Python :: 3.3",
			"Programming Language :: Python :: 3.4",
			"Programming Language :: Python :: Implementation :: CPython",
			"Programming Language :: Python :: Implementation :: PyPy",
			"Topic :: Internet :: WWW/HTTP :: WSGI",
			"Topic :: Software Development :: Libraries :: Python Modules",
		],
	
	packages = find_packages(exclude=['documentation', 'example', 'test']),
	include_package_data = True,
	namespace_packages = [
			'web',  # primary namespace
			'web.app',  # reusable components
			'web.command',  # extensible command-line interface and scripts
			'web.ext',  # frameowrk extensions
		],
	
	entry_points = {
			# WebCore reusable application components.
			'web.app': [
					'locale.settings = web.app.locale.settings:LocaleSettings',  # "User Preferences" data endpoints.
					'locale.console = web.app.locale.console:LocaleConsole',  # Web-based message catalog management.
				],
			
			# WebCore extension registration.
			# This extension manages context additions, browser-based settings detection, REPL and debugger additions,
			# and also manages the GILT "inspector panel".
			'web.extension': [
					'locale = web.ext.locale:LocaleExtension',
				],
			
			# Command-line scripts for administrative purposes.
			'web.command': [
					'cldr = cldr.update:update_cldr_dataset[cli]',  # Explore the Unicode CLDR datasets.
					'translate = web.command.translate:translate[cli]',  # Query your application's message catalogs.
				],
			
			# Additional command support/integration.
			'web.clean': [
					# Running `web clean` will remove compiled catalogs.
					'messages = web.command.locale:clean_messages[cli]',
				],
			
			'web.collect': [
					# Running `web collect` will extract messages and update the message catalog sources.
					'messages = web.command.locale:collect_messages[cli]',
				],
			
			'web.compile': [
					# Running `web compile` will compile message catalogs into efficient binary forms.
					'messages = web.command.locale:compile_messages[cli]',
				],
		},
	
	install_requires = [
			'marrow.package<2.0',  # dynamic execution and plugin management
			
			'xmltodict',  # Simple XML to Python object conversion.
			'webob',  # HTTP Accept header parsing
			'babel',  # general internationalized formats, gettext catalog support
			'money',  # internationalized money format
			'pytz',  # timezone support
			'l18n',  # Unicode CLDR datasets and common lazy string evaluation
			'language-tags',  # IETF BCP-47 language tags
			'babelfish',  # common Lanugage and Country abstraction
		],
	
	extras_require = dict(
			development = tests_require,
			
			# Message catalog formats.  Use via extras definition: `web.locale[po,yaml]`
			po = [],  # Included for completeness.
			yaml = ['pyyaml'],  # YAML definition support.
			json = ['pyslate'],  # JSON definition support.
			mongo = ['pymongo>=3.0'],  # MongoDB-based definition support.
			
			# Feature tags.
			cli = ['web.command']
		),
	
	tests_require = tests_require,
	
	dependency_links = [
		],
	
	zip_safe = True,
	cmdclass = dict(
			test = PyTest,
		)
)

