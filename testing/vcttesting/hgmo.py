# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, unicode_literals

import errno
import json
import os
import uuid

import concurrent.futures as futures
import ldap
import paramiko


HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))


class HgCluster(object):
    """Interface to a cluster of HG servers.

    This class manages Docker contains and environments that replicate the
    hg.mozilla.org server configuration.
    """
    MASTER_FILE_MAP = {
        'hgext/pushlog-legacy/buglink.py': '/repo/hg/extensions/buglink.py',
        'hgext/pushlog-legacy/hgwebjson.py': '/repo/hg/extensions/hgwebjson.py',
        'hgext/pushlog-legacy/pushlog-feed.py': '/repo/hg/extensions/pushlog-feed.py',
        'hgext/pushlog/__init__.py': '/repo/hg/extensions/pushlog/__init__.py',
        'hgext/serverlog/__init__.py': '/repo/hg/extensions/serverlog/__init__.py',
        'scripts/pash/pash.py': '/usr/local/bin/pash.py',
        'scripts/pash/hg_helper.py': '/usr/local/bin/hg_helper.py',
        'scripts/pash/ldap_helper.py': '/usr/local/bin/ldap_helper.py',
        'scripts/pash/repo_group.py': '/usr/local/bin/repo_group.py',
        'scripts/pash/sh_helper.py': '/usr/local/bin/sh_helper.py',
    }

    def __init__(self, docker, state_path=None, ldap_image=None,
                 master_image=None, web_image=None):
        self._d = docker
        self._dc = docker.client
        self.state_path = state_path

        if state_path and os.path.exists(state_path):
            with open(state_path, 'rb') as fh:
                state = json.load(fh)
                for k, v in state.items():
                    setattr(self, k, v)
        else:
            self.ldap_image = ldap_image
            self.master_image = master_image
            self.web_image = web_image
            self.ldap_id = None
            self.master_id = None
            self.web_ids = []
            self.ldap_uri = None
            self.master_ssh_hostname = None
            self.master_ssh_port = None
            self.web_urls = []

    def start(self, ldap_port=None, master_ssh_port=None, web_count=2,
              coverage=False):
        """Start the cluster.

        If ``coverage`` is True, code coverage for Python executions will be
        obtained.
        """

        ldap_image = self.ldap_image
        master_image = self.master_image
        web_image = self.web_image

        if not ldap_image or not master_image or not web_image:
            images = self._d.build_hgmo(verbose=True)
            master_image = images['hgmaster']
            web_image = images['hgweb']
            ldap_image = images['ldap']

        with futures.ThreadPoolExecutor(4) as e:
            f_ldap_create = e.submit(self._dc.create_container, ldap_image)

            env = {}
            if coverage:
                env['CODE_COVERAGE'] = '1'

            f_master_create = e.submit(self._dc.create_container,
                                       master_image,
                                       environment=env)
            f_web_creates = []
            for i in range(web_count):
                f_web_creates.append(e.submit(self._dc.create_container,
                                              web_image))

            ldap_id = f_ldap_create.result()['Id']
            master_id = f_master_create.result()['Id']

            # Start LDAP first because we need to link it to all the hg
            # containers.
            self._dc.start(ldap_id, port_bindings={389: ldap_port})
            ldap_state = self._dc.inspect_container(ldap_id)

            self._dc.start(master_id,
                           links=[(ldap_state['Name'], 'ldap')],
                           port_bindings={22: master_ssh_port})

            master_state = self._dc.inspect_container(master_id)

            web_ids = [f.result()['Id'] for f in f_web_creates]
            fs = []
            for i in web_ids:
                fs.append(e.submit(self._dc.start, i,
                                   links=[(master_state['Name'], 'master')],
                                   port_bindings={22: None, 80: None}))
            [f.result() for f in fs]

            f_web_states = []
            for i in web_ids:
                f_web_states.append(e.submit(self._dc.inspect_container, i))

            web_states = [f.result() for f in f_web_states]

        with futures.ThreadPoolExecutor(4) as e:
            f_private_key = e.submit(self._d.get_file_content, master_id, '/etc/mercurial/mirror')
            f_public_key = e.submit(self._d.get_file_content, master_id, '/etc/mercurial/mirror.pub')

        mirror_private_key = f_private_key.result()
        mirror_public_key = f_public_key.result()

        # Reconcile state across all the containers.
        with futures.ThreadPoolExecutor(web_count + 1) as e:
            # Update the SSH key for the "hg" user on the web containers.
            cmd = [
                '/set-mirror-key.py',
                mirror_private_key,
                mirror_public_key,
            ]
            for i in web_ids:
                e.submit(self._dc.execute(i, cmd))

            # Tell the master about all the mirrors.
            mirrors = [s['NetworkSettings']['IPAddress'] for s in web_states]
            e.submit(self._dc.execute, master_id, ['/set-mirrors.py'] + mirrors)

        ldap_ports = ldap_state['NetworkSettings']['Ports']
        master_ssh_ports = master_state['NetworkSettings']['Ports']

        ldap_host_port = ldap_ports['389/tcp'][0]['HostPort']
        master_ssh_host_port = master_ssh_ports['22/tcp'][0]['HostPort']

        self.ldap_uri = 'ldap://%s:%s/' % (self._d.docker_hostname,
                                           ldap_host_port)
        self.create_vcs_sync_login(mirror_public_key)

        self.ldap_image = ldap_image
        self.master_image = master_image
        self.web_image = web_image
        self.ldap_id = ldap_id
        self.master_id = master_id
        self.web_ids = web_ids
        self.master_ssh_hostname = self._d.docker_hostname
        self.master_ssh_port = master_ssh_host_port
        self.web_urls = []
        for s in web_states:
            port = s['NetworkSettings']['Ports']['80/tcp'][0]['HostPort']
            self.web_urls.append('http://%s:%s/' % (self._d.docker_hostname,
                                                    port))

        return self._write_state()

    def stop(self):
        """Stop the cluster.

        Containers will be shut down gracefully.
        """
        c = self._d.client
        with futures.ThreadPoolExecutor(4) as e:
            e.submit(c.stop, self.master_id)
            e.submit(c.stop, self.ldap_id)
            for i in self.web_ids:
                e.submit(c.stop, i)

    def clean(self):
        """Clean the cluster.

        Containers will be shut down and removed. The state file will
        destroyed.
        """
        c = self._d.client
        with futures.ThreadPoolExecutor(4) as e:
            e.submit(c.remove_container, self.master_id, force=True)
            e.submit(c.remove_container, self.ldap_id, force=True)
            for i in self.web_ids:
                e.submit(c.remove_container, i, force=True)

        try:
            os.unlink(self.state_path)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

        self.ldap_id = None
        self.master_id = None
        self.web_ids = []
        self.ldap_uri = None
        self.master_ssh_hostname = None
        self.master_ssh_port = None

    def _write_state(self):
        assert self.state_path
        s = {
                'ldap_image': self.ldap_image,
                'master_image': self.master_image,
                'web_image': self.web_image,
                'ldap_id': self.ldap_id,
                'master_id': self.master_id,
                'web_ids': self.web_ids,
                'ldap_uri': self.ldap_uri,
                'master_ssh_hostname': self.master_ssh_hostname,
                'master_ssh_port': self.master_ssh_port,
                'web_urls': self.web_urls,
        }
        with open(self.state_path, 'wb') as fh:
            json.dump(s, fh, sort_keys=True, indent=4)

        return s

    @property
    def ldap(self):
        assert self.ldap_uri
        c = ldap.initialize(self.ldap_uri)
        c.simple_bind_s('cn=admin,dc=mozilla', 'password')

        return c

    def create_ldap_user(self, email, username, uid, fullname,
                         key_filename=None, scm_level=None):
        """Create a new user in LDAP.

        The user has an ``email`` address, a full ``name``, a
        ``username`` (for system accounts) and a numeric ``uid``.
        """

        dn = 'mail=%s,o=com,dc=mozilla' % email

        r = [
            (b'objectClass', [
                b'hgAccount',
                b'inetOrgPerson',
                b'organizationalPerson',
                b'person',
                b'posixAccount',
                b'top',
            ]),
            (b'cn', [fullname]),
            (b'fakeHome', [b'/tmp']),
            (b'gidNumber', [b'100']),
            (b'hgAccountEnabled', [b'TRUE']),
            (b'hgHome', [b'/tmp']),
            (b'hgShell', [b'/bin/sh']),
            (b'homeDirectory', [b'/home/%s' % username]),
            (b'sn', [fullname.split()[-1]]),
            (b'uid', [username]),
            (b'uidNumber', [str(uid)]),
        ]

        self.ldap.add_s(dn, r)

        if key_filename:
            pubkey_filename = '%s.pub' % key_filename
            if os.path.exists(key_filename):
                with open(pubkey_filename, 'rb') as fh:
                    pubkey = fh.read()
            else:
                k = paramiko.rsakey.RSAKey.generate(2048)
                k.write_private_key_file(key_filename)
                pubkey = '%s %s %s' % (k.get_name(), k.get_base64(), email)
                pubkey = pubkey.encode('utf-8')
                with open(pubkey_filename, 'wb') as fh:
                    fh.write(pubkey)

            self.add_ssh_key(email, pubkey)

        if scm_level:
            if scm_level < 1 or scm_level > 3:
                raise ValueError('scm level must be between 1 and 3: %s' %
                                 scm_level)

            for level in range(1, scm_level + 1):
                group = b'scm_level_%d' % level
                self.add_user_to_ldap_group(email, group)

    def create_vcs_sync_login(self, pubkey):
        dn = 'uid=vcs-sync,ou=logins,dc=mozilla'

        r = [
            (b'objectClass', [
                b'account',
                b'top',
                b'uidObject',
                b'hgAccount',
                b'mailObject',
                b'posixAccount',
                b'ldapPublicKey',
            ]),
            (b'cn', [b'VCS Sync']),
            (b'fakeHome', [b'/tmp']),
            (b'gidNumber', [b'100']),
            (b'hgAccountEnabled', [b'TRUE']),
            (b'hgHome', [b'/tmp']),
            (b'hgShell', [b'/bin/sh']),
            (b'homeDirectory', [b'/home/vcs-sync']),
            (b'mail', [b'vcs-sync@mozilla.com']),
            (b'uidNumber', [b'1500']),
            (b'sshPublicKey', [pubkey]),
        ]

        self.ldap.add_s(dn, r)

    def add_ssh_key(self, email, key):
        """Add an SSH key to a user in LDAP."""
        dn = 'mail=%s,o=com,dc=mozilla' % email

        c = self.ldap
        modlist = []

        try:
            existing = c.search_s(dn, ldap.SCOPE_BASE)[0][1]
            if b'ldapPublicKey' not in existing[b'objectClass']:
                modlist.append((ldap.MOD_ADD, b'objectClass', b'ldapPublicKey'))
        except ldap.NO_SUCH_OBJECT:
            pass

        modlist.append((ldap.MOD_ADD, b'sshPublicKey', key))

        c.modify_s(dn, modlist)

    def add_user_to_ldap_group(self, member, group):
        """Add a user to the specified LDAP group.

        The ``group`` is defined in terms of its ``cn`` under
        ``ou=groups,dc=mozilla`. e.g. ``scml_level_3``.
        """
        dn = 'cn=%s,ou=groups,dc=mozilla' % group

        modlist = [(ldap.MOD_ADD, b'memberUid', member)]
        self.ldap.modify_s(dn, modlist)

    def create_repo(self, name, level=1):
        """Create a repository on the cluster.

        ``path`` is the path fragment the repository would be accessed under
        at https://hg.mozilla.org. e.g. ``hgcustom/version-control-tools``.

        The repository will be owned by an appropriate ``scm_level_N`` group
        according to the ``level`` specified.
        """
        if level < 1 or level > 3:
            raise ValueError('level must be between 1 and 3')

        cmd = ['/create-repo', name, 'scm_level_%d' % level]

        self._dc.execute(self.master_id, cmd)

    def aggregate_code_coverage(self, destdir):
        master_map = {}
        for host, container in self.MASTER_FILE_MAP.items():
            master_map[container] = os.path.join(ROOT, host)

        for c in self._d.get_code_coverage(self.master_id, filemap=master_map):
            dest = os.path.join(destdir, 'coverage.%s' % uuid.uuid1())
            c.write_file(dest)
