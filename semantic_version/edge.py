import itertools

from . import base
from sortedcontainers import SortedDict
from sortedcontainers import SortedSet

def solve(pkgsVersionsDeps, root):
    state = State(pkgsVersionsDeps)
    state.attempt_pkg_traversal(root)
    return state.pkgsLocked


def initialize_edges(pkgsVersionsSpecs):
    """Helper function to initialize a map of edges."""
    return {
        pkg: {
            version: {
                dep: Edges.from_specs(specs)
                for (dep, specs) in depsSpecs.items()
            }
            for (version, depsSpecs) in pkgVersionsSpecs.items()
        }
        for (pkg, pkgVersionsSpecs) in pkgsVersionsSpecs.items()
    }


class NotSolved(Exception):
    """No solution was found in this branch"""


class EdgeLt(base.VersionReq):
    def __init__(self, version):
        self.kind = self.KIND_LT
        self.version = version.force_non_partial()

    def __cmp__(self, other):
        assert isinstance(other, EdgeLt)
        return self.version.__cmp__(other.version)


class EdgeGte(base.VersionReq):
    def __init__(self, version):
        self.kind = self.KIND_GTE
        self.version = version.force_non_partial()

    def __cmp__(self, other):
        assert isinstance(other, EdgeGte)
        return self.version.__cmp__(other.version)


class Edges(object):
    """The _potentially_ required versions in a constraint solving system.

    This is (essentially) collection of VersionReq's that have been converted
    to their "edges" EdgeLt or EdgeGte.

    This object consumes VersionReqs, converting them to their simpler form
    and removing duplicates. The purpose is _not_ to filter on these directly,
    but rather to pass these constraints to a system which can return
    versions which match the requirements.

    When spec's are added, they are converted to their graph edge.  All KINDs
    are converted to one of Eq, LT or GTE
    - ANY is converted to ``>=0.0.1``
    - EQ becomes GTE ``==1.2.3 becomes >=1.2.3``
    - NEQ is exclusive: ``!=1.2.3 becomes <1.2.3,>=1.2.4``
    - GT becomes GTE the bumped patch. ``>1.2.3 becomes >=1.2.4``
    - LTE becomes LT the bumped patch. ``<=2.0.0 becomes <2.0.1``
    - EMPTY is converted to CARET (which is converted)
    - CARET is converted to two ReqVersions: ``^1.2.3 becomes >=1.2.3,<2.0.0``
    - TILTE is converted to two ReqVersions: ``~1.2.3 becomes >=1.2.3,<1.3.0``
    - KIND_COMPATIBLE is converted similar to CARET
    """
    def __init__(self):
        self.reqs_lt = set()
        self.reqs_gte = set()

    @classmethod
    def from_specs(cls, specs):
        edges = cls()
        self.extend(specs)
        return edges

    def extend(self, specs):
        for spec in specs:
            self.append(spec)

    def append(self, reqOrSpec):
        """Note: Appending a req can cause up to two reqs being added."""
        if isinstance(reqOrSpec, base.Spec):
            for req in reqOrSpec.requirements:
                self.append(req)
            return
        req = reqOrSpec.force_non_partial()

        # TODO: the "next patch" stuff here may want to preserve builds, etc in
        # some way??
        version = req.version
        if version and version.partial:
            # partial requirement versions change the hash since
            # prerelease and build get set to different things.
            raise TypeError("Partial req versions are not allowed")
        kind = req.kind
        a_lt = self.reqs_lt.add
        a_gte = self.reqs_gte.add

        if kind == req.KIND_LT:
            a_lt(EdgeLt(version))

        elif kind == req.KIND_GTE:
            a_gte(EdgeGte(version))

        elif kind == req.KIND_EQUAL or kind == req.KIND_SHORTEQ:
            a_gte(EdgeGte(version))

        elif kind == req.KIND_NEQ:
            a_lt(EdgeLt(version))
            a_gte(EdgeGte(version.next_patch()))

        elif kind == req.KIND_ANY:
            a_gte(EdgeGte(base.Version(0, 0, 1)))

        elif kind == req.KIND_LTE:
            a_lt(EdgeLt(version.next_patch()))

        elif kind == req.KIND_GT:
            a_gte(EdgeGte(version.next_patch()))

        elif kind == req.KIND_CARET:
            if version.major != 0:
                upper = version.next_major()
            elif version.minor != 0:
                upper = version.next_minor()
            else:
                upper = version.next_patch()
            a_gte(EdgeGte(version))
            a_lt(EdgeLt(upper))

        elif kind == req.KIND_TILDE:
            a_gte(EdgeGte(version))
            a_lt(EdgeLt(version.next_minor()))

        elif kind == req.KIND_COMPATIBLE:
            if version.patch is not None:
                upper = version.next_minor()
            else:
                upper = version.next_major()
            a_gte(EdgeGte(version))
            a_lt(EdgeLt(upper))

        else:  # pragma: no cover
            raise ValueError('Unexpected match kind: %r' % kind)

    def __repr__(self):
        return "Edges({})".format(
            ', '.join(str(r) for r in iter(self))
        )

    def __iter__(self):
        return itertools.chain(
            self.reqs_lt,
            self.reqs_gte,
        )


class PkgsVersionDepsMap(dict):
    """A dictionary tree representing `pkgs -> version -> dependencies -> container`.

    The container is typically `Edges` or an SortedSet.

    This is the common format for representing edges and (eventually) versions.
    """

    def new_function(self):
        raise NotImplementedError()

    def extend_function(self, a):
        raise NotImplementedError()

    def update(self, pkgsVersionsMap):
        for (pkg, pkgVersionsMap) in pkgsVersionsMap.items():
            if pkg not in self:
                self[pkg] = {}
            sPkgVersionsMap = self[pkg]

            for (version, depsMap) in pkgVersionsMap.items():
                if version not in sPkgVersionsMap:
                    sPkgVersionsMap[version] = {}
                sPkgDepsMap = sPkgVersionsMap[version]

                for (dep, specs) in depsMap.items():
                    if dep not in sPkgDepsMap:
                        sPkgDepsMap[dep] = self.new_function()
                    self.extend_function(sPkgDepsMap[dep], specs)


class PkgsVersionsDepsVersions(dict):
    def filter_update(self, root, pkgsVersionsSpecs, pkgsVersions):
        """Given a new (possibly updated) set of pkgsVersionsSpecs, update the
        avilable versions.
        """

        for (pkg, pkgVersionsSpecs) in pkgsVersionsSpecs.items():
                if pkg not in self:
                    self[pkg] = {}
                sPkgVersionsDeps = self[pkg]

                for (version, depsSpecs) in pkgVersionsSpecs.items():
                    if version not in sPkgVersionsDeps:
                        sPkgVersionsDeps[version] = {}
                    sDepsVersions = sPkgVersionsDeps[version]

                    for (dep, specs) in depsSpecs.items():
                        if dep == root:
                            continue
                        if dep not in sDepsVersions:
                            sDepsVersions[dep] = SortedSet()

                        sDepsVersions[dep].update(
                            filter_by_specs(specs, pkgsVersions[dep])
                        )

def filter_by_specs(specs, versions):
    for version in versions:
        if version_matches_specs(specs, version):
            yield version

def version_matches_specs(specs, version):
    for spec in specs:
        if not spec.match(version):
            return False
    return True

class PkgsVersionDepsSet(PkgsVersionDepsMap):
    def new_function(self):
        return set()

    def extend_function(self, mySet, a):
        set.update(mySet, a)



class PkgsVersionDepsOrderedSet(PkgsVersionDepsMap):
    def new_function(self):
        return SortedSet()

    def extend_function(self, sortedSet, a):
        SortedSet.update(sortedSet, a)


class PkgsEdges(PkgsVersionDepsMap):
    """For ingesting specs to create edges."""
    def extend_specs(self, pkg, specs):
        if pkg not in self:
            self[pkg] = Edges()
        self[pkg].extend(specs)

    def update(self, pkgsVersionsSpecs):
        """Consume a complex tree of specs to build out the edges."""
        for (pkg, pkgVersionsSpecs) in pkgsVersionsSpecs.items():
            for (version, depsSpecs) in pkgVersionsSpecs.items():
                for (dep, specs) in depsSpecs.items():
                    self.extend_specs(dep, specs)


class PkgsEdgeVersions(dict):
    """Edge versions for specific pkgs.

    These are the versions the server has.
    """
    def update(self, pkgsVersions):
        for pkg, versions in pkgsVersions.items():
            if pkg not in self_map:
                self[pkg] = SortedSet()
            self[pkg].update(versions)


def retrieve_edge_versions(retrieve_fn, pkgEdges):
    """Retrieve the edges from the server, returning
    the versions.
    """
    return {
        pkg: retrieve_fn(pkg, edges)
        for (pkg, edges) in pkgEdges.items()
    }


class State(object):
    def __init__(self, pkgsVersionsDeps):
        self.pkgsVersionsDeps = pkgsVersionsDeps
        self.pkgsLocked = {
            pkg: None for pkg in pkgsVersionsDeps.keys()
        }
        self.failedVersions = {
            pkg: set() for pkg in pkgsVersionsDeps.keys()
        }

    def attempt_pkg_traversal(self, pkg):
        lockedVersion = self.pkgsLocked[pkg]
        if lockedVersion is not None:
            # this pkg has already been locked, attempt to use that version.
            self.attempt_pkgVersion_traversal(pkg, lockedVersion)
            return  # no error == success

        for pkgVersion in self.pkgsVersionsDeps[pkg].keys():
            if pkgVersion in self.failedVersions[pkg]:
                continue

            assert self.pkgsLocked[pkg] == None
            self.pkgsLocked[pkg] = pkgVersion
            try:
                self.attempt_pkgVersion_traversal(pkg, pkgVersion)
                return  # this pkgVersion combination was successful
            except NotSolved:
                self._handle_not_solved()

        raise NotSolved()

    def attempt_pkgVersion_traversal(self, pkg, pkgVersion):
        depsVersions = self.pkgsVersionsDeps[pkg][pkgVersion]
        lockedHere = []

        for dep, depVersions in depsVersions.items():
            lockedDepVersion = self.pkgsLocked[dep]
            if lockedDepVersion is not None:
                if lockedDepVersion in depVersions:
                    # One of our dependencies was locked, and we can use the
                    # locked version.
                    #
                    # Note: we are _within_ the attempt to lock the dependency
                    # at this version.
                    continue
                else:
                    raise NotSolved()

            for depVersion in reversed(depVersions):
                if depVersion in self.failedVersions[dep]:
                    continue

                self.pkgsLocked[dep] = depVersion
                try:
                    self.attempt_pkg_traversal(dep)
                    lockedHere.append(dep)
                    break
                except NotSolved:
                    self._handle_not_solved(dep, depVersion)
            else:
                # `for...else` The `break` was never hit, the dependency was
                # never solved.
                #
                # The dependency was not solved by us. Make sure we clean up
                # all the dependencies we locked and add them to failed
                #
                # TODO: should I add to the failedVersions all versions we
                # locked?
                #
                # I feel like no, somehow these don't "count" as attempts for
                # that version.
                #
                # I think that is true -- we were not trying to solve _for_
                # these, they were just version combinations we _attempted_.
                # Honestly I was looking for a piece of code that _didn't_
                # set failedVersions, letting us try out combinations... this
                # is it!
                for dep in lockedHere:
                    self.pkgsLocked[dep] = None
                raise NotSolved()

    def _handle_not_solved(self, pkg, pkgVersion):
        self.pkgsLocked[pkg] = None
        self.failedVersions[pkg].add(pkgVersion)

