# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

"""make Mozilla contributors more productive

This extension adds Mozilla-centric commands and functionality to Mercurial
to enable contributors to Firefox and related applications to be more
productive.

Included are commands that interface with Mozilla's automation infrastructure.
These allow developers to quickly check the status of repositories and builds
without having to leave the comfort of the terminal.

Known Mozilla Repositories
==========================

This extension teaches Mercurial about known Mozilla repositories.

Each main mozilla-central clone is given a common name. e.g. "mozilla-central"
becomes "central" and "mozilla-inbound" becomes "inbound." In addition,
repositories have short aliases to quickly refer to them. e.g.
"mozilla-central" is can be references by "m-c" or "mc."

The mechanism to resolve a repository string to a repository instance is
supplemented with these known aliases. For example, to pull from
mozilla-central, you can simply run `hg pull central`. There is no need to set
up the [paths] section in your hgrc!

To view the list of known repository aliases, run `hg moztrees`.

Unified Repositories
====================

Gecko code is developed in parallel across a number of repositories that are
cloned from the canonical repository, mozilla-central. Seasoned developers
typically interact with multiple repositories.

This extension provides mechanisms to create and maintain a single Mercurial
repository that contains changesets from multiple "upstream" repositories.

The recommended method to create a unified repository is to run `hg
cloneunified`. This will pull changesets from all major release branches and
mozilla-inbound.

Once you have a unified repository, you can pull changesets from repositories
by using `hg pull`, likely by specifying one of the tree aliases (see `hg
moztrees`).

One needs to be careful when pushing changesets when operating a unified
repository. By default, `hg push` will attempt to push all local changesets not
in a remote. This is obviously not desired (you wouldn't want to push
mozilla-central to mozilla-beta)! Instead, you'll want to limit outgoing
changesets to a specific head or revision. You can specify `hg push -r REV`.

Remote References
=================

When pulling from known Gecko repositories, this extension automatically
creates references to branches on the remote. These can be referenced via
the revision <tree>/<name>. e.g. 'central/default'.

Remote refs are read-only and are updated automatically during repository pull
and push operations.

This feature is similar to Git remote refs.

Pushlog Data
============

This extension supports downloading pushlog data from Mozilla's repositories.
Pushlog data records who pushed changesets where and when.

To use this functionality, you'll need to sync pushlog data from the server to
the local machine. This facilitates rapid data lookup and can be done by
running `hg pushlogsync`.

Once pushlog data is synced, you can use `hg changesetpushes` to look up push
information for a specific changeset.

Bug Info
========

Information about bugs is extracted from commit messages as changesets are
introduced into the repository. You can look up information about specific
bugs via `hg buginfo`.

Revisions Sets
==============

This extension adds the following revision set selectors functions.

bug(BUG)
   Retreive changesets that reference a specific bug. e.g. ``bug(784841)``.

dontbuild()
   Retrieve changesets that are marked as DONTBUILD.

me()
   Retrieve changesets that you are involved with.

   This retrieves changesets you authored (via ui.username) as well as
   changesets you reviewed (via mozext.ircnick).

nobug()
   Retrieve changesets that don't reference a bug in the commit message.

pushhead([TREE])
   Retrieve changesets that are push heads.

firstpushdate(DATE)
   Retrieve changesets that were first pushed according to the date spec.

firstpushtree(TREE)
   Retrieve changesets that initially landed on the specified tree.

pushdate(DATE)
   Retrieve changesets that were pushed according to the date spec.

reviewer(REVIEWER)
   Retrieve changesets there were reviewed by the specified person.

   The reviewer string matches the *r=* string specified in the commit. In
   the future, we may consult a database of known aliases, etc.

reviewed()
   Retrieve changesets that have a reviewer marked.

tree(TREE)
   Retrieve changesets that are currently in the specified tree.

   Trees are specified with a known alias. e.g. ``tree(central)``.

   It's possible to see which changesets are in some tree but not others.
   e.g. to find changesets in *inbound* that haven't merged to *central*
   yet, do ``tree(inbound) - tree(central)``.

Templates
=========

This extension provides keywords that can used with templates.

bug
   The bug primarily associated with a changeset.

bugs
   All the bugs associated with a changeset.

firstrelease
   The version number of the first release channel release a changeset
   was present in.

firstbeta
   The version number of the first beta channel release a changeset was
   present in.

firstaurora
   The version number of the first aurora channel release a changeset was
   present in.

firstnightly
   The version number of the first nightly channel release a changeset was
   present in.

auroradate
   The date of the first Aurora a changeset was likely present in.

   This value may not be accurate. The value is currently obtained by
   querying the pushlog data to see when a changeset was pushed to this
   channel. The date of the next Aurora is then calculated from that
   (essentially looking for the next early morning Pacific time day).
   Aurora releases are not always consistent. A more robust method of
   calculation involves grabbing information from release engineering
   servers.

nightlydate
   The date of the first Nightly a changeset was likely present in.

   See auroradate for accuracy information.

firstpushuser
   The username of the first person who pushed this changeset.

firstpushtree
   The name of the first tree this changeset was pushed to.

firstpushtreeherder
   The URL of the Treeherder results for the first push of this changeset.

firstpushdate
   The date of the first push of this changeset.

pushdates
   The list of dates a changeset was pushed.

pushheaddates
   The list of dates a changeset was pushed as a push head.

trees
   The list of trees a changeset has landed in.

reltrees
   The list of release trees a changeset has landed in.

This extension provides the following template functions:

dates(VALUES, [format, [sep]])
   Format a list of dates.

   If the second argument is defined, the specified date formatting
   string will be used. Else, it defaults to '%Y-%m-%d'.

   If the third argument is defined, elements will be separated by the
   specified string. Else, ',' is used.

Config Options
==============

This extension consults the following config options.

mozext.headless
   Indicates that this extension is running in *headless* mode. *headless*
   mode is intended for server operation, not local development.

mozext.ircnick
   Your Mozilla IRC nickname. This string value will be used to look for
   your reviews and patches.

mozext.disable_local_database
   When this boolean flag is true, the local SQLite database indexing
   useful lookups (such as bugs and pushlog info) is not enabled.

mozext.reject_pushes_with_repo_names
   This boolean is used to enable a ``prepushkey`` hook that prevents
   pushes to keys (bookmarks, tags, etc) whose name is prefixed with that
   of an official Mozilla repository.

   This hook is useful for servers exposing a monolithic repository where
   each separate Mozilla repository is exposed through bookmarks and where
   the server does not want to allow external users from changing the
   *canonical* refs.

   For example, with this flag set, pushes to bookmarks ``central/default``
   and ``inbound/foobar`` will be rejected because they begin with the names
   of official Mozilla repositories. However, pushes to the bookmark
   ``gps/test`` will be allowed.
"""

import calendar
import datetime
import errno
import os
import shutil

from operator import methodcaller

from mercurial.i18n import _
from mercurial.error import (
    ParseError,
    RepoError,
)
from mercurial.localrepo import (
    repofilecache,
)
from mercurial.node import (
    bin,
    hex,
    short,
)
from mercurial import (
    configitems,
    demandimport,
    encoding,
    error,
    exchange,
    extensions,
    hg,
    registrar,
    revset,
    scmutil,
    sshpeer,
    templatefilters,
    templatekw,
    util,
)

# TRACKING hg46
try:
    sshpeertype = sshpeer.sshv1peer
except AttributeError:
    sshpeertype = sshpeer.sshpeer

OUR_DIR = os.path.normpath(os.path.dirname(__file__))
with open(os.path.join(OUR_DIR, '..', 'bootstrap.py')) as f:
    exec(f.read())

from mozhg.util import (
    import_module,
    get_backoutbynode,
)

# TRACKING hg47
templateutil = import_module('mercurial.templateutil')

# TRACKING hg47
# util.makedate -> utils.dateutils.makedate
# util.matchdate -> utils.dateutils.matchdate
dateutil = import_module('mercurial.utils.dateutil')
if dateutil:
    makedate = dateutil.makedate
    matchdate = dateutil.matchdate
else:
    makedate = util.makedate
    matchdate = util.matchdate


# Disable demand importing for mozautomation because "requests" doesn't
# play nice with the demand importer.
with demandimport.deactivated():
    from mozautomation.changetracker import (
        ChangeTracker,
    )

    from mozautomation.commitparser import (
        parse_bugs,
        parse_reviewers,
    )

    from mozautomation.repository import (
        MercurialRepository,
        RELEASE_TREES,
        REPOS,
        resolve_trees_to_official,
        resolve_trees_to_uris,
        resolve_uri_to_tree,
        treeherder_url,
        TREE_ALIASES,
    )

bz_available = False

testedwith = '4.4 4.5 4.6 4.7'
minimumhgversion = '4.4'
buglink = 'https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer%20Services&component=Mercurial%3A%20mozext'

cmdtable = {}

command = registrar.command(cmdtable)

revsetpredicate = registrar.revsetpredicate()
templatekeyword = registrar.templatekeyword()
templatefunc = registrar.templatefunc()

configtable = {}
configitem = registrar.configitem(configtable)

configitem('mozext', 'headless',
           default=configitems.dynamicdefault)
configitem('mozext', 'ircnick',
           default=None)
configitem('mozext', 'disable_local_database',
           default=False)
configitem('mozext', 'reject_pushes_with_repo_names',
           default=False)
configitem('mozext', 'backoutsearchlimit',
           default=configitems.dynamicdefault)

colortable = {
    'buildstatus.success': 'green',
    'buildstatus.failed': 'red',
    'buildstatus.testfailed': 'cyan',
}


# Override peer path lookup such that common names magically get resolved to
# known URIs.
old_peerorrepo = hg._peerorrepo

def get_ircnick(ui):
    headless = ui.configbool('mozext', 'headless')
    ircnick = ui.config('mozext', 'ircnick')
    if not ircnick and not headless:
        raise error.Abort(_('Set "[mozext] ircnick" in your hgrc to your '
            'Mozilla IRC nickname to enable additional functionality.'))
    return ircnick

def peerorrepo(ui, path, *args, **kwargs):
    # Always try the old mechanism first. That way if there is a local
    # path that shares the name of a magic remote the local path is accessible.
    try:
        return old_peerorrepo(ui, path, *args, **kwargs)
    except RepoError:
        tree, uri = resolve_trees_to_uris([path])[0]

        if not uri:
            raise

        path = uri
        return old_peerorrepo(ui, path, *args, **kwargs)

hg._peerorrepo = peerorrepo


def exchangepullpushlog(orig, pullop):
    res = orig(pullop)

    if not pullop.remote.capable('pushlog'):
        return res

    # stepsdone added in Mercurial 3.2.
    if hasattr(pullop, 'stepsdone') and 'pushlog' in pullop.stepsdone:
        return res

    repo = pullop.repo

    tree = resolve_uri_to_tree(pullop.remote.url())
    if not tree or not repo.changetracker or tree == "try":
        return res

    # Calling wire protocol commands via SSH requires the server-side wire
    # protocol code to be known by the client. The server-side code is defined
    # by the pushlog extension, so we effectively need the pushlog extension
    # enabled to call the wire protocol method when pulling via SSH. We don't
    # (yet) recommend installing the pushlog extension locally. Furthermore,
    # pulls from hg.mozilla.org should be performed via https://, not ssh://.
    # So just bail on pushlog fetching if pulling via ssh://.
    if isinstance(pullop.remote, sshpeertype):
        pullop.repo.ui.warn('cannot fetch pushlog when pulling via ssh://; '
                            'you should be pulling via https://\n')
        return res

    lastpushid = repo.changetracker.last_push_id(tree)
    fetchfrom = lastpushid + 1 if lastpushid is not None else 0

    lines = pullop.remote._call('pushlog', firstpush=str(fetchfrom))
    lines = iter(lines.splitlines())

    statusline = lines.next()
    if statusline[0] == '0':
        raise error.Abort('remote error fetching pushlog: %s' % lines.next())
    elif statusline != '1':
        raise error.Abort('error fetching pushlog: unexpected response: %s\n' %
            statusline)

    pushes = []
    for line in lines:
        pushid, who, when, nodes = line.split(' ', 3)
        nodes = [bin(n) for n in nodes.split()]

        # Verify incoming changesets are known and stop processing when we see
        # an unknown changeset. This can happen when we're pulling a former
        # head instead of all changesets.
        try:
            [repo[n] for n in nodes]
        except error.RepoLookupError:
            repo.ui.warn('received pushlog entry for unknown changeset; ignoring\n')
            break

        pushes.append((int(pushid), who, int(when), nodes))

    if pushes:
        repo.changetracker.add_pushes(tree, pushes)
        repo.ui.status('added %d pushes\n' % len(pushes))

    return res

@command('moztrees', [], _('hg moztrees'), norepo=True)
def moztrees(ui, **opts):
    """Show information about Mozilla source trees."""
    longest = max(len(tree) for tree in REPOS.keys())
    ui.write('%s  %s\n' % (_('Repo').rjust(longest), _('Aliases')))

    for name in sorted(REPOS):
        aliases = []
        for alias, targets in TREE_ALIASES.items():
            if len(targets) > 1:
                continue

            if targets[0] == name:
                aliases.append(alias)

        ui.write('%s: %s\n' % (name.rjust(longest),
            ', '.join(sorted(aliases))))


@command('cloneunified', [], _('hg cloneunified [DEST]'), norepo=True)
def cloneunified(ui, dest='gecko', **opts):
    """Clone main Mozilla repositories into a unified local repository.

    This command will clone the most common Mozilla repositories and will
    add changesets and remote tracking markers into a common repository.

    If the destination path is not given, 'gecko' will be used.

    This command is effectively an alias for a number of other commands.
    However, due to the way Mercurial internally stores data, it is recommended
    to run this command to ensure optimal storage of data.
    """
    path = ui.expandpath(dest)
    repo = hg.repository(ui, path, create=True)

    success = False

    try:
        for tree in ('esr17', 'b2g18', 'release', 'beta', 'aurora', 'central',
            'inbound'):
            peer = hg.peer(ui, {}, tree)
            ui.warn('Pulling from %s.\n' % peer.url())
            repo.pull(peer)
        res = hg.update(repo, repo.lookup('central/default'))
        success = True
        return res
    finally:
        if not success:
            shutil.rmtree(path)


@command('treestatus', [], _('hg treestatus [TREE] ...'), norepo=True)
def treestatus(ui, *trees, **opts):
    """Show the status of the Mozilla repositories.

    If trees are open, it is OK to land code on them.

    If trees require approval, you'll need to obtain approval from
    release management to land changes.

    If trees are closed, you shouldn't push unless you are fixing the reason
    the tree is closed.
    """
    from mozautomation.treestatus import TreeStatusClient

    client = TreeStatusClient()
    status = client.all()

    trees = resolve_trees_to_official(trees)

    if trees:
        for k in set(status.keys()) - set(trees):
            del status[k]
    if not status:
        raise error.Abort('No status info found.')

    longest = max(len(s) for s in status)

    for tree in sorted(status):
        s = status[tree]
        if s.status == 'closed':
            ui.write('%s: %s (%s)\n' % (tree.rjust(longest), s.status,
                s.reason))
        else:
            ui.write('%s: %s\n' % (tree.rjust(longest), s.status))


@command('treeherder', [], _('hg treeherder [TREE] [REV]'))
def treeherder(ui, repo, tree=None, rev=None, **opts):
    """Open Treeherder showing build status for the specified revision.

    The command receives a tree name and a revision to query. The tree is
    required because a revision/changeset may existing in multiple
    repositories.
    """
    if not tree:
        raise error.Abort('A tree must be specified.')

    if not rev:
        raise error.Abort('A revision must be specified.')

    tree, repo_url = resolve_trees_to_uris([tree])[0]
    if not repo_url:
        raise error.Abort("Don't know about tree: %s" % tree)

    r = MercurialRepository(repo_url)
    node = repo[rev].hex()
    push = r.push_info_for_changeset(node)

    if not push:
        raise error.Abort("Could not find push info for changeset %s" % node)

    push_node = push.last_node

    url = treeherder_url(tree, push_node)

    import webbrowser
    webbrowser.get('firefox').open(url)


@command('pushlogsync', [
    ('', 'reset', False, _('Wipe and repopulate the pushlog database.'), ''),
], _('hg pushlogsync'))
def syncpushinfo(ui, repo, tree=None, **opts):
    """Synchronize the pushlog information for all known Gecko trees.

    The pushlog info contains who, when, and where individual changesets were
    pushed.

    After running this command, you can query for push information for specific
    changesets.
    """
    if not repo.changetracker:
        ui.warn('Local database appears to be disabled.')
        return 1

    if opts['reset']:
        repo.changetracker.wipe_pushlog()
        return

    for i, tree in enumerate(sorted(REPOS)):
        repo.changetracker.load_pushlog(tree)
        ui.progress('pushlogsync', i, total=len(REPOS))

    ui.progress('pushlogsync', None)


def print_changeset_pushes(ui, repo, rev, all=False):
    if not repo.changetracker:
        ui.warn('Local database appears to be disabled.')
        return 1

    ctx = repo[rev]
    node = ctx.node()

    pushes = repo.changetracker.pushes_for_changeset(node)
    pushes = [p for p in pushes if all or p[0] in RELEASE_TREES]
    if not pushes:
        ui.warn('No pushes recorded for changeset: ', str(ctx), '\n')
        return 1

    longest_tree = max(len(p[0]) for p in pushes) + 2
    longest_user = max(len(p[3]) for p in pushes) + 2

    ui.write(str(ctx.rev()), ':', str(ctx), ' ', ctx.description(), '\n')

    ui.write('Release ', 'Tree'.ljust(longest_tree), 'Date'.ljust(20),
            'Username'.ljust(longest_user), 'Build Info\n')
    for tree, push_id, when, user, head_node in pushes:
        releases = set()
        release = ''
        versions = {}

        if tree == 'beta':
            versions = repo._beta_releases()
        elif tree == 'release':
            versions = repo._release_releases()

        for version, e in versions.items():
            vctx = repo[e[0]]
            if ctx.descendant(vctx):
                releases.add(version)

        if len(releases):
            release = sorted(releases)[0]

        url = treeherder_url(tree, hex(head_node))
        date = datetime.datetime.fromtimestamp(when)
        ui.write(release.ljust(8), tree.ljust(longest_tree), date.isoformat(),
            ' ', user.ljust(longest_user), url or '', '\n')


@command('changesetpushes',
    [('a', 'all', False, _('Show all trees, not just release trees.'), '')],
    _('hg changesetpushes REV'))
def changesetpushes(ui, repo, rev, all=False, **opts):
    """Display pushlog information for a changeset.

    This command prints pushlog entries for a given changeset. It is used to
    answer the question: how did a changeset propagate to all the trees.
    """
    print_changeset_pushes(ui, repo, rev, all=all)


@command('buginfo', [
    ('a', 'all', False, _('Show all trees, not just release trees.'), ''),
    ('', 'reset', False, _('Wipe and repopulate the bug database.'), ''),
    ('', 'sync', False, _('Synchronize the bug database.'), ''),
    ], _('hg buginfo [BUG] ...'))
def buginfo(ui, repo, *bugs, **opts):
    if not repo.changetracker:
        ui.warning('Local database appears to be disabled')
        return 1

    if opts['sync']:
        repo.sync_bug_database()
        return

    if opts['reset']:
        repo.reset_bug_database()
        return

    tracker = repo.changetracker

    nodes = set()
    for bug in bugs:
        nodes |= set(tracker.changesets_with_bug(bug))

    # Sorting by topological order would probably be preferred. This is quick
    # and easy.
    contexts = sorted([repo[node] for node in nodes], key=methodcaller('rev'))

    for ctx in contexts:
        print_changeset_pushes(ui, repo, ctx.rev(), all=opts['all'])
        ui.write('\n')


@command('mybookmarks', [], _('hg mybookmarks'))
def mybookmarks(ui, repo):
    """Show bookmarks that belong to me.

    A common developer workflow involves creating bookmarks to track
    feature work. A busy repository may have bookmarks belonging to many
    people. This command provides a mechanism to easily query for bookmarks
    belonging to you.

    A bookmark belonging to you is one whose name begins with your configured
    IRC nick or has you as the author of the bookmark's changeset.
    """
    nick = get_ircnick(ui)
    prefix = '%s/' % nick
    me = ui.config('ui', 'username')

    for bookmark, node in sorted(repo._bookmarks.iteritems()):
        user = repo[node].user()

        if user != me and not bookmark.startswith(prefix):
            continue

        ui.write('%-50s %d:%s\n' % (
            bookmark, repo[node].rev(), short(node)))


@command('prunerelbranches', [], _('hg prunerelbranches'))
def prunerelbranches(ui, repo):
    """Prune release branch references from the local repo.

    Old repos with mozext.refs_as_bookmarks but not
    mozext.skip_relbranch_bookmarks may have undesired bookmarks pointed to
    release branches. Running this command will prune release branch bookmarks
    from this repository.
    """
    repo.prune_relbranch_refs()


def reject_repo_names_hook(ui, repo, namespace=None, key=None, old=None,
        new=None, **kwargs):
    """prepushkey hook that prevents changes to reserved names.

    Names that begin with the name of a repository identifier are rejected.
    """
    if key.lower().startswith(tuple(REPOS.keys())):
        ui.warn('You are not allowed to push tags or bookmarks that share '
            'names with official Mozilla repositories: %s\n' % key)
        return True

    return False

def wrappedpull(orig, repo, remote, *args, **kwargs):
    """Wraps exchange.pull to add remote tracking refs."""
    if not hasattr(repo, 'changetracker'):
        return orig(repo, remote, *args, **kwargs)

    old_rev = len(repo)
    res = orig(repo, remote, *args, **kwargs)
    lock = repo.wlock()
    try:
        tree = resolve_uri_to_tree(remote.url())

        if tree:
            repo._update_remote_refs(remote, tree)

        # Sync bug info.
        for rev in repo.changelog.revs(old_rev + 1):
            ctx = repo[rev]
            bugs = parse_bugs(ctx.description())
            if bugs and repo.changetracker:
                repo.changetracker.associate_bugs_with_changeset(bugs,
                    ctx.node())

    finally:
        lock.release()

    return res

def wrappedpush(orig, repo, remote, *args, **kwargs):
    if not hasattr(repo, 'changetracker'):
        return orig(repo, remote, *args, **kwargs)

    res = orig(repo, remote, *args, **kwargs)
    lock = repo.wlock()
    try:
        tree = resolve_uri_to_tree(remote.url())

        if tree:
            repo._update_remote_refs(remote, tree)

    finally:
        lock.release()

    return res

class remoterefs(dict):
    """Represents a remote refs file."""

    def __init__(self, repo):
        dict.__init__(self)
        self._repo = repo

        try:
            for line in repo.vfs('remoterefs'):
                line = line.strip()
                if not line:
                    continue

                sha, ref = line.split(None, 1)
                ref = encoding.tolocal(ref)
                try:
                    self[ref] = repo.changelog.lookup(sha)
                except LookupError:
                    pass

        except IOError as e:
            if e.errno != errno.ENOENT:
                raise

    def write(self):
        f = self._repo.vfs('remoterefs', 'w', atomictemp=True)
        for ref in sorted(self):
            f.write('%s %s\n' % (hex(self[ref]), encoding.fromlocal(ref)))
        f.close()


@revsetpredicate('bug(N)')
def revset_bug(repo, subset, x):
    """Changesets referencing a specified Bugzilla bug. e.g. bug(123456)."""
    err = _('bug() requires an integer argument.')
    bugstring = revset.getstring(x, err)

    try:
        bug = int(bugstring)
    except Exception:
        raise ParseError(err)

    def fltr(x):
        # We do a simple string test first because avoiding regular expressions
        # is good for performance.
        desc = repo[x].description()
        return bugstring in desc and bug in parse_bugs(desc)

    return subset.filter(fltr)


@revsetpredicate('dontbuild()')
def revset_dontbuild(repo, subset, x):
    if x:
        raise ParseError(_('dontbuild() does not take any arguments'))

    return subset.filter(lambda x: 'DONTBUILD' in repo[x].description())


@revsetpredicate('me()')
def revset_me(repo, subset, x):
    """Changesets that you are involved in."""
    if x:
        raise ParseError(_('me() does not take any arguments'))

    me = repo.ui.config('ui', 'username')
    if not me:
        raise error.Abort(_('"[ui] username" must be set to use me()'))

    ircnick = get_ircnick(repo.ui)

    n = encoding.lower(me)
    kind, pattern, matcher = revset._substringmatcher(n)

    def fltr(x):
        ctx = repo[x]
        if matcher(encoding.lower(ctx.user())):
            return True

        return ircnick in parse_reviewers(ctx.description())

    return subset.filter(fltr)


@revsetpredicate('nobug()')
def revset_nobug(repo, subset, x):
    if x:
        raise ParseError(_('nobug() does not take any arguments'))

    return subset.filter(lambda x: not parse_bugs(repo[x].description()))


def revset_tree(repo, subset, x):
    """``tree(X)``
    Changesets currently in the specified Mozilla tree.

    A tree is the name of a repository. e.g. ``central``.
    """
    err = _('tree() requires a string argument.')
    tree = revset.getstring(x, err)

    tree, uri = resolve_trees_to_uris([tree])[0]
    if not uri:
        raise error.Abort(_("Don't know about tree: %s") % tree)

    ref = '%s/default' % tree

    head = repo[ref].rev()
    ancestors = set(repo.changelog.ancestors([head], inclusive=True))

    return subset & revset.baseset(ancestors)


def revset_firstpushdate(repo, subset, x):
    """``firstpushdate(DATE)``
    Changesets that were initially pushed according to the date spec provided.
    """
    ds = revset.getstring(x, _('firstpushdate() requires a string'))
    dm = matchdate(ds)

    def fltr(x):
        pushes = list(repo.changetracker.pushes_for_changeset(repo[x].node()))

        if not pushes:
            return False

        when = pushes[0][2]

        return dm(when)

    return subset.filter(fltr)


def revset_firstpushtree(repo, subset, x):
    """``firstpushtree(X)``
    Changesets that were initially pushed to tree X.
    """
    tree = revset.getstring(x, _('firstpushtree() requires a string argument.'))

    tree, uri = resolve_trees_to_uris([tree])[0]
    if not uri:
        raise error.Abort(_("Don't know about tree: %s") % tree)

    def fltr(x):
        pushes = list(repo.changetracker.pushes_for_changeset(
            repo[x].node()))

        if not pushes:
            return False

        return pushes[0][0] == tree

    return subset.filter(fltr)


def revset_pushdate(repo, subset, x):
    """``pushdate(DATE)``
    Changesets that were pushed according to the date spec provided.

    All pushes are examined.
    """
    ds = revset.getstring(x, _('pushdate() requires a string'))
    dm = matchdate(ds)

    def fltr(x):
        for push in repo.changetracker.pushes_for_changeset(repo[x].node()):
            when = push[2]

            if dm(when):
                return True

        return False

    return subset.filter(fltr)


def revset_pushhead(repo, subset, x):
    """``pushhead([TREE])``
    Changesets that are push heads.

    A push head is a changeset that was a head when it was pushed to a
    repository. In other words, the automation infrastructure likely
    kicked off a build using this changeset.

    If an argument is given, we limit ourselves to pushes on the specified
    tree.

    If no argument is given, we return all push heads for all trees. Note that
    a changeset can be a push head multiple times. This function doesn't care
    where the push was made if no argument was given.
    """
    # We have separate code paths because the single tree path uses a single
    # query and is faster.
    if x:
        tree = revset.getstring(x, _('pushhead() requires a string argument.'))
        tree, uri = resolve_trees_to_uris([tree])[0]

        if not uri:
            raise error.Abort(_("Don't know about tree: %s") % tree)

        def pushheads():
            for push_id, head_changeset in repo.changetracker.tree_push_head_changesets(tree):
                try:
                    head = repo[head_changeset].rev()
                    yield head
                except error.RepoLookupError:
                    # There are some malformed pushes.  Ignore them.
                    continue

        # Push heads are returned in order of ascending push ID, which
        # corresponds to ascending commit order in hg.
        return subset & revset.generatorset(pushheads(), iterasc=True)
    else:
        def is_pushhead(r):
            node = repo[r].node()
            for push in repo.changetracker.pushes_for_changeset(node):
                if str(push[4]) == node:
                    return True
            return False

        return subset.filter(is_pushhead)


@revsetpredicate('reviewer(REVIEWER)')
def revset_reviewer(repo, subset, x):
    """Changesets reviewed by a specific person."""
    n = revset.getstring(x, _('reviewer() requires a string argument.'))

    return subset.filter(lambda x: n in parse_reviewers(repo[x].description()))


@revsetpredicate('reviewed()')
def revset_reviewed(repo, subset, x):
    """Changesets that were reviewed."""
    if x:
        raise ParseError(_('reviewed() does not take an argument'))

    return subset.filter(lambda x: list(parse_reviewers(repo[x].description())))


@templatekeyword('bug')
def template_bug(repo, ctx, **args):
    """:bug: String. The bug this changeset is most associated with."""
    bugs = parse_bugs(ctx.description())
    return bugs[0] if bugs else None


@templatekeyword('backedoutby')
def template_backedoutby(repo, ctx, **args):
    return get_backoutbynode('mozext', repo, ctx)


@templatekeyword('bugs')
def template_bugs(repo, ctx, **args):
    """:bugs: List of ints. The bugs associated with this changeset."""
    bugs = parse_bugs(ctx.description())

    # TRACKING hg47
    if templateutil:
        bugs = templateutil.hybridlist(bugs, 'bugs')

    return bugs


@templatekeyword('reviewer')
def template_reviewer(repo, ctx, **args):
    """:reviewer: String. The first reviewer of this changeset."""
    reviewers = parse_reviewers(ctx.description())
    try:
        first_reviewer = next(reviewers)
        return first_reviewer
    except StopIteration:
        return None


@templatekeyword('reviewers')
def template_reviewers(repo, ctx, **args):
    """:reviewers: List of strings. The reviewers associated with tis
    changeset."""
    # TRACKING hg47
    if templateutil:
        return templateutil.mappinggenerator(parse_reviewers, args=(ctx.description(),))
    else:
        return parse_reviewers(ctx.description())


def _compute_first_version(repo, ctx, what, cache):
    rev = ctx.rev()
    cache_key = '%s_ancestors' % what

    if cache_key not in cache:
        versions = getattr(repo, '_%s_releases' % what)()
        cache[cache_key] = repo._earliest_version_ancestors(versions)

    for version, ancestors in cache[cache_key].items():
        if rev in ancestors:
            return version

    return None


def template_firstrelease(repo, ctx, **args):
    """:firstrelease: String. The version of the first release channel
    release with this changeset.
    """
    return _compute_first_version(repo, ctx, 'release', args['cache'])


def template_firstbeta(repo, ctx, **args):
    """:firstbeta: String. The version of the first beta release with this
    changeset.
    """
    return _compute_first_version(repo, ctx, 'beta', args['cache'])


def _calculate_push_milestone(repo, ctx, tree):
    # This function appears to be slow. Consider caching results.
    pushes = repo.changetracker.pushes_for_changeset(ctx.node())
    pushes = [p for p in pushes if p[0] == tree]

    if not pushes:
        return None

    push = pushes[0]

    return repo._revision_milestone(str(push[4]))


def template_firstaurora(repo, ctx, **args):
    """:firstaurora: String. The version of the first aurora release with
    this changeset.
    """
    return _calculate_push_milestone(repo, ctx, 'aurora')


def template_firstnightly(repo, ctx, **args):
    """:firstnightly: String. The version of the first nightly release
    with this changeset.
    """
    return _calculate_push_milestone(repo, ctx, 'central')


def _calculate_next_daily_release(repo, ctx, tree):
    pushes = repo.changetracker.pushes_for_changeset(ctx.node())
    pushes = [p for p in pushes if p[0] == tree]

    if not pushes:
        return None

    push = pushes[0]
    when = push[2]

    dt = datetime.datetime.utcfromtimestamp(when)

    # Daily builds kick off at 3 AM in Mountain View. This is -7 hours
    # from UTC during daylight savings and -8 during regular.
    # Mercurial nor core Python have timezone info built-in, so we
    # hack this calculation together here. This calculation is wrong
    # for date before 2007, when the DST start/end days changed. It
    # may not always be correct in the future. We should use a real
    # timezone database.
    dst_start = None
    dst_end = None

    c = calendar.Calendar(calendar.SUNDAY)
    sunday_count = 0
    for day in c.itermonthdates(dt.year, 3):
        if day.month != 3:
            continue

        if day.weekday() == 6:
            sunday_count += 1
            if sunday_count == 2:
                dst_start = day
                break

    for day in c.itermonthdates(dt.year, 11):
        if day.month != 11:
            if day.weekday() == 6:
                dst_end = day
                break

    dst_start = datetime.datetime(dst_start.year, dst_start.month,
        dst_start.day, 2)
    dst_end = datetime.datetime(dst_end.year, dst_end.month,
        dst_end.day, 2)

    is_dst = dt >= dst_start and dt <= dst_end
    utc_offset = 11 if is_dst else 10

    if dt.hour > 3 + utc_offset:
        dt += datetime.timedelta(days=1)

    return dt.date().isoformat()


def template_auroradate(repo, ctx, **args):
    """:auroradate: String. The date of the first Aurora this
    changeset was likely first active in as a YYYY-MM-DD value.
    """
    return _calculate_next_daily_release(repo, ctx, 'aurora')


def template_nightlydate(repo, ctx, **args):
    """:nightlydate: Date information. The date of the first Nightly this
    changeset was likely first active in as a YYYY-MM-DD value.
    """
    return _calculate_next_daily_release(repo, ctx, 'central')


def template_firstpushuser(repo, ctx, **args):
    """:firstpushuser: String. The first person who pushed this changeset.
    """
    pushes = list(repo.changetracker.pushes_for_changeset(ctx.node()))

    if not pushes:
        return None

    return pushes[0][3]


def template_firstpushtree(repo, ctx, **args):
    """:firstpushtree: String. The first tree this changeset was pushed to.
    """
    pushes = list(repo.changetracker.pushes_for_changeset(ctx.node()))

    if not pushes:
        return None

    return pushes[0][0]


def template_firstpushtreeherder(repo, ctx, **args):
    """:firstpushtreeherder: String. Treeherder URL for the first push of this changeset.
    """
    pushes = list(repo.changetracker.pushes_for_changeset(ctx.node()))
    if not pushes:
        return None

    push = pushes[0]
    tree, node = push[0], push[4]

    return treeherder_url(tree, hex(node))


def template_firstpushdate(repo, ctx, **args):
    """:firstpushdate: Date information. The date of the first push of this
    changeset."""
    pushes = list(repo.changetracker.pushes_for_changeset(ctx.node()))
    if not pushes:
        return None

    return makedate(pushes[0][2])


def template_pushdates(repo, ctx, **args):
    """:pushdates: List of date information. The dates this changeset was
    pushed to various trees."""
    pushes = repo.changetracker.pushes_for_changeset(ctx.node())
    pushdates = [makedate(p[2]) for p in pushes]

    # TRACKING hg47
    if templateutil:
        pushdates = templateutil.hybridlist(pushdates, 'pushdates')

    return pushdates


def template_pushheaddates(repo, ctx, **args):
    """:pushheaddates: List of date information. The dates this changeset
    was pushed to various trees as a push head."""
    node = ctx.node()
    pushes = repo.changetracker.pushes_for_changeset(ctx.node())
    pushheaddates = [makedate(p[2]) for p in pushes if str(p[4]) == node]

    # TRACKING hg47
    if templateutil:
        pushheaddates = templateutil.hybridlist(pushheaddates, 'pushheaddates')

    return pushheaddates


def template_trees(repo, ctx, **args):
    """:trees: List of strings. Trees this changeset has landed in.
    """
    trees = [p[0] for p in repo.changetracker.pushes_for_changeset(ctx.node())]

    # TRACKING hg47
    if templateutil:
        trees = templateutil.hybridlist(trees, 'trees')

    return trees


def template_reltrees(repo, ctx, **args):
    """:reltrees: List of strings. Release trees this changeset has landed in.
    """
    reltrees = [t for t in template_trees(repo, ctx, **args) if t in RELEASE_TREES]

    # TRACKING hg47
    if templateutil:
        reltrees = templateutil.hybridlist(reltrees, 'reltrees')

    return reltrees


# [gps] This function may not be necessary. However, I was unable to figure out
# how to do the equivalent with regular template syntax. Yes, I tried the
# list operator.
@templatefunc('dates(VALUES, [fmt, [sep]])')
def template_dates(context, mapping, args):
    """Format a list of dates"""
    if not (1 <= len(args) <= 3):
        raise ParseError(_("dates expects one, two, or three arguments"))

    fmt = '%Y-%m-%d'
    sep = ','

    if len(args) > 1:
        fmt = templatefilters.stringify(args[1][0](context, mapping,
            args[1][1]))
    if len(args) > 2:
        sep = templatefilters.stringify(args[2][0](context, mapping,
            args[2][1]))

    return sep.join(util.datestr(d, fmt) for d in args[0][0](context, mapping,
        args[0][1]))

def extsetup(ui):
    global bz_available
    try:
        extensions.find('bzexport')
        bz_available = True
    except KeyError:
        pass

    extensions.wrapfunction(exchange, 'pull', wrappedpull)
    extensions.wrapfunction(exchange, 'push', wrappedpush)
    extensions.wrapfunction(exchange, '_pullobsolete', exchangepullpushlog)

    if not ui.configbool('mozext', 'disable_local_database'):
        revset.symbols['pushhead'] = revset_pushhead
        revset.symbols['tree'] = revset_tree
        revset.symbols['firstpushdate'] = revset_firstpushdate
        revset.symbols['firstpushtree'] = revset_firstpushtree
        revset.symbols['pushdate'] = revset_pushdate

    if not ui.configbool('mozext', 'disable_local_database'):
        templatekw.keywords['firstrelease'] = template_firstrelease
        templatekw.keywords['firstbeta'] = template_firstbeta
        templatekw.keywords['firstaurora'] = template_firstaurora
        templatekw.keywords['firstnightly'] = template_firstnightly
        templatekw.keywords['auroradate'] = template_auroradate
        templatekw.keywords['nightlydate'] = template_nightlydate
        templatekw.keywords['firstpushuser'] = template_firstpushuser
        templatekw.keywords['firstpushtree'] = template_firstpushtree
        templatekw.keywords['firstpushtreeherder'] = template_firstpushtreeherder
        templatekw.keywords['firstpushdate'] = template_firstpushdate
        templatekw.keywords['pushdates'] = template_pushdates
        templatekw.keywords['pushheaddates'] = template_pushheaddates
        templatekw.keywords['trees'] = template_trees
        templatekw.keywords['reltrees'] = template_reltrees

def reposetup(ui, repo):
    """Custom repository implementation.

    Our custom repository class tracks remote tree references so users can
    reference specific revisions on remotes.
    """

    if not repo.local():
        return

    orig_findtags = repo._findtags
    orig_lookup = repo.lookup

    class remotestrackingrepo(repo.__class__):
        @repofilecache('remoterefs')
        def remoterefs(self):
            return remoterefs(self)

        @util.propertycache
        def changetracker(self):
            if ui.configbool('mozext', 'disable_local_database'):
                return None
            try:
                return ChangeTracker(self.vfs.join('changetracker.db'))
            except Exception as e:
                raise error.Abort(e.message)

        def _update_remote_refs(self, remote, tree):
            existing_refs = set()
            incoming_refs = set()

            for ref in self.remoterefs:
                if ref.startswith('%s/' % tree):
                    existing_refs.add(ref)

            for branch, nodes in remote.branchmap().items():
                # Don't store RELBRANCH refs for non-release trees, as they are
                # meaningless and cruft from yesteryear.
                if branch.endswith('RELBRANCH'):
                    if tree not in TREE_ALIASES['releases']:
                        continue

                ref = '%s/%s' % (tree, branch)
                incoming_refs.add(ref)

                for node in nodes:
                    self.remoterefs[ref] = node

            # Prune old refs.
            for ref in existing_refs - incoming_refs:
                try:
                    del self.remoterefs[ref]
                except KeyError:
                    pass

            with self.wlock():
                self.remoterefs.write()

        def _revision_milestone(self, rev):
            """Look up the Gecko milestone of a revision."""
            fctx = self.filectx('config/milestone.txt', changeid=rev)
            lines = fctx.data().splitlines()
            lines = [l for l in lines if not l.startswith('#') and l.strip()]

            if not lines:
                return None

            return lines[0]

        def _beta_releases(self):
            """Obtain information for each beta release."""
            return self._release_versions('beta/')

        def _release_releases(self):
            return self._release_versions('release/')

        def _release_versions(self, prefix):
            d = {}

            for key, node in self.remoterefs.items():
                if not key.startswith(prefix):
                    continue

                key = key[len(prefix):]

                if not key.startswith('GECKO') or not key.endswith('RELBRANCH'):
                    continue

                version, date, _relbranch = key.split('_')
                version = version[5:]
                after = ''
                marker = ''

                if 'b' in version:
                    marker = 'b'
                    version, after = version.split('b')

                if len(version) > 2:
                    major, minor = version[0:2], version[2:]
                else:
                    major, minor = version

                version = '%s.%s' % (major, minor)
                if marker:
                    version += '%s%s' % (marker, after)

                d[version] = (key, node, major, minor, marker or None, after or None)

            return d

        def _earliest_version_ancestors(self, versions):
            """Take a set of versions and generate earliest version ancestors.

            This function takes the output of _release_versions as an input
            and calculates the set of revisions corresponding to each version's
            introduced ancestors. Put another way, it returns a dict of version
            to revision set where each set is disjoint and presence in a
            version's set indicates that particular version introduced that
            revision.

            This computation is computational expensive. Callers are encouraged
            to cache it.
            """
            d = {}
            seen = set()
            for version, e in sorted(versions.items()):
                version_rev = self[e[1]].rev()
                ancestors = set(self.changelog.findmissingrevs(
                    common=seen, heads=[version_rev]))
                d[version] = ancestors
                seen |= ancestors

            return d

        def reset_bug_database(self):
            if not self.changetracker:
                return

            self.changetracker.wipe_bugs()
            self.sync_bug_database()

        def sync_bug_database(self):
            if not self.changetracker:
                return

            for rev in self:
                ui.progress('changeset', rev, total=len(self))
                ctx = self[rev]
                bugs = parse_bugs(ctx.description())
                if bugs:
                    self.changetracker.associate_bugs_with_changeset(bugs,
                        ctx.node())

            ui.progress('changeset', None)

        def prune_relbranch_refs(self):
            todelete = [bm for bm in self._bookmarks.keys()
                        if bm.endswith('RELBRANCH')]
            with self.wlock(), self.lock():
                with self.transaction('prunerelbranch') as tr:
                    for bm in todelete:
                        ui.warn('Removing bookmark %s\n' % bm)

                    changes = [(bm, None) for bm in todelete]
                    self._bookmarks.applychanges(self, tr, changes)

                todelete = [ref for ref in self.remoterefs.keys()
                            if ref.endswith('RELBRANCH')]

                for ref in todelete:
                    del self.remoterefs[ref]

                self.remoterefs.write()


    repo.__class__ = remotestrackingrepo

    if ui.configbool('mozext', 'reject_pushes_with_repo_names'):
        ui.setconfig('hooks', 'prepushkey.reject_repo_names',
            reject_repo_names_hook)

    # Set up a specially named path so reviewboard resolves this repo to
    # mozilla-central.
    if not ui.config('paths', 'reviewboard'):
        uri = resolve_trees_to_uris(['central'])[0][1]
        ui.setconfig('paths', 'reviewboard', uri)
