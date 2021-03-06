"""Tests for syncing npm. Requires a `pip install ijson`, which requires yajl. Good luck! :^)
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from subprocess import Popen, PIPE

from gratipay.testing import Harness
from gratipay.package_managers import readmes


def load(raw):
    serialized = Popen( ('env/bin/sync-npm', 'serialize', '/dev/stdin')
                      , stdin=PIPE, stdout=PIPE
                       ).communicate(raw)[0]
    Popen( ('env/bin/sync-npm', 'upsert', '/dev/stdin')
         , stdin=PIPE, stdout=PIPE
          ).communicate(serialized)[0]


class Tests(Harness):

    def test_packages_starts_empty(self):
        assert self.db.all('select * from packages') == []


    # sn - sync-npm

    def test_sn_inserts_packages(self):
        load(br'''
        { "_updated": 1234567890
        , "testing-package":
            { "name":"testing-package"
            , "description":"A package for testing"
            , "maintainers":[{"email":"alice@example.com"}]
            , "author": {"email":"bob@example.com"}
            , "time":{"modified":"2015-09-12T03:03:03.135Z"}
             }
         }
        ''')

        package = self.db.one('select * from packages')
        assert package.package_manager == 'npm'
        assert package.name == 'testing-package'
        assert package.description == 'A package for testing'
        assert package.name == 'testing-package'


    def test_sn_handles_quoting(self):
        load(br'''
        { "_updated": 1234567890
        , "testi\\\"ng-pa\\\"ckage":
            { "name":"testi\\\"ng-pa\\\"ckage"
            , "description":"A package for \"testing\""
            , "maintainers":[{"email":"alice@\"example\".com"}]
            , "author": {"email":"\\\\\"bob\\\\\"@example.com"}
            , "time":{"modified":"2015-09-12T03:03:03.135Z"}
             }
         }
        ''')

        package = self.db.one('select * from packages')
        assert package.package_manager == 'npm'
        assert package.name == r'testi\"ng-pa\"ckage'
        assert package.description == 'A package for "testing"'
        assert package.emails == ['alice@"example".com', r'\\"bob\\"@example.com']


    def test_sn_handles_empty_description_and_emails(self):
        load(br'''
        { "_updated": 1234567890
        , "empty-description":
            { "name":"empty-description"
            , "description":""
            , "time":{"modified":"2015-09-12T03:03:03.135Z"}
             }
         }
        ''')

        package = self.db.one('select * from packages')
        assert package.package_manager == 'npm'
        assert package.name == 'empty-description'
        assert package.description == ''
        assert package.emails == []


    # rs - readmes.Syncer

    def test_rs_syncs_a_readme(self):
        self.db.run("INSERT INTO packages (package_manager, name, description, emails) "
                    "VALUES ('npm', 'foo-package', 'A package', ARRAY[]::text[])")

        class DirtyPackage:
            package_manager = 'npm'
            name = 'foo-package'

        def fetch(name):
            return {'name': 'foo-package', 'readme': '# Greetings, program!'}

        readmes.Syncer(self.db)(DirtyPackage(), fetch=fetch)

        package = self.db.one('SELECT * FROM packages')
        assert package.name == 'foo-package'
        assert package.description == 'A package'
        assert package.readme == '<h1 id="user-content-greetings-program" class="deep-link">' \
                                 '<a href="#greetings-program">Greetings, program!</a></h1>\n'
        assert package.readme_raw == '# Greetings, program!'
        assert package.readme_type == 'x-markdown/npm'
        assert package.emails == []
